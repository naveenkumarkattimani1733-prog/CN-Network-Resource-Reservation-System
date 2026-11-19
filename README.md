# Project 15 — Network Resource Reservation System

**Team 18:** AM443, AM502, AM472  
**Protocol:** TCP  
**Network lab:** Mininet + Open vSwitch  
**SDN controller:** OS-Ken (OpenFlow 1.3)

## 1. What this project does

Three client hosts request a temporary amount of bandwidth from a reservation server. The server checks the configured 100 Mbps capacity and rejects requests that would overbook it. When a request is accepted, the server asks the SDN controller to update the Open vSwitch QoS queues and OpenFlow rules. A reservation can also be released manually or expire automatically.

This is a teaching prototype running inside one Mininet virtual network. It does not reserve bandwidth on the real campus network or the physical Internet.

## 2. Network layout

```text
 h1 (client)  --\
 h2 (client)  ---+--- s1 (Open vSwitch) --- h4 (TCP reservation server)
 h3 (client)  --/            |
                             | OpenFlow 1.3
                             v
                       OS-Ken controller
```

- `h1`, `h2`, `h3`: send reservation requests.
- `h4`: runs the TCP reservation server at `10.0.0.4:5000`.
- `s1`: forwards packets and applies QoS queues on the port connected to h4.
- OS-Ken: controller that installs queue and flow policies.
- Default available capacity: **100 Mbps**.

## 3. Files in this ZIP — what each one is for

| File | Why it is needed |
|---|---|
| `client.py` | Command-line client. Sends reserve, release, status and list requests over TCP. |
| `server.py` | TCP server on h4. Accepts multiple clients concurrently and runs the expiry timer. |
| `reservation_manager.py` | Main reservation logic: capacity checking, conflict rejection, locking, release and expiry. |
| `config.py` | Shared settings: capacity, IP addresses, ports and queue IDs. |
| `sdn_client.py` | Sends policy updates from the reservation server to the controller over a local Unix socket. |
| `controller/reservation_controller.py` | OS-Ken SDN application. Configures OVS QoS queues and OpenFlow 1.3 rules. |
| `topology/run_mininet.py` | Creates h1–h4 and s1 in Mininet, connects the controller and starts the server inside h4. |
| `scripts/setup_ubuntu.sh` | Installs Mininet, Open vSwitch, iperf3 and the OS-Ken Python environment. |
| `scripts/start_controller.sh` | Starts the SDN controller. |
| `scripts/run_mininet.sh` | Starts the Mininet topology. |
| `scripts/cleanup.sh` | Cleans up Mininet and temporary project files after the controller is stopped. |
| `requirements.txt` | Lists the Python controller dependency installed by the setup script. |
| `tests/test_reservation_manager.py` | Optional automated tests for allocation, rejection, concurrency, release, expiry and controller failure rollback. |
| `README.md` | This setup, usage, demo and file-explanation guide. |

The folders are used to keep the controller code, topology code, setup scripts and tests separate. No generated files or virtual-environment folders are included.

## 4. Before you start

Use an **Ubuntu 22.04 VM** with internet access and at least 2 CPU cores and 4 GB RAM if possible. The supplied college Mininet guide covers installing Mininet on Ubuntu, but this project also needs OS-Ken; the included setup script installs it. The script requires Python 3.10 or newer, so Ubuntu 22.04 is the straightforward choice.

Run the project inside Ubuntu, not in the normal Windows Command Prompt or PowerShell.

### Move and extract the ZIP

1. Copy this ZIP into your Ubuntu VM (download it in the VM browser, or use your VM's shared folder).
2. Extract it into your Ubuntu home folder. The extracted folder must be named `Network_Resource_Reservation_System_MINIMAL`.
3. Open Terminal and run:

```bash
cd ~/Network_Resource_Reservation_System_MINIMAL
pwd
```

Keep the path printed by `pwd`. You will use it in the Mininet client commands below. In the examples, replace `<PROJECT_PATH>` with that exact path, without angle brackets.

Check Ubuntu and Python:

```bash
lsb_release -a
python3 --version
```

Check that the VM has internet:

```bash
ping -c 3 google.com
```

If Ubuntu reports Python earlier than 3.10, stop here and use an Ubuntu 22.04 VM rather than continuing with this setup script.

## 5. Install the requirements — do this once

From the project folder:

```bash
chmod +x scripts/*.sh
./scripts/setup_ubuntu.sh
```

The script installs Mininet, Open vSwitch, iperf3, Python virtual-environment support and OS-Ken. It creates `.venv/` inside the project folder. You do not need to install Mininet a second time using a separate method if this script completes successfully.

## 6. Start the project — every demo session

Open **two Ubuntu terminal windows**. In both terminals, first enter the project folder:

```bash
cd ~/Network_Resource_Reservation_System_MINIMAL
```

### Terminal 1 — SDN controller

```bash
./scripts/start_controller.sh
```

Leave this terminal open. It runs the OS-Ken controller and listens for the OpenFlow 1.3 switch.

### Terminal 2 — Mininet and reservation server

```bash
./scripts/run_mininet.sh
```

Wait until the `mininet>` prompt appears. The topology script starts the TCP reservation server inside h4.

At the `mininet>` prompt, check connectivity:

```text
pingall
```

Expected: all four hosts should reach each other, with 0% packet loss. If there is packet loss, do not continue with the reservation demo yet; check that Terminal 1's controller is still running.

## 7. Main demonstration — copy these commands

For each command below, replace `<PROJECT_PATH>` with the path you copied from `pwd`, for example `/home/student/Network_Resource_Reservation_System_MINIMAL`.

### Demo 1 — accept a reservation

```text
mininet> h1 python3 <PROJECT_PATH>/client.py reserve --bandwidth 30 --duration 120
```

Expected: accepted. Note the reservation ID printed in the response.

### Demo 2 — accept a second reservation

```text
mininet> h2 python3 <PROJECT_PATH>/client.py reserve --bandwidth 40 --duration 120
mininet> h1 python3 <PROJECT_PATH>/client.py status
```

Expected status:

- Total capacity: 100 Mbps
- Reserved: 70 Mbps
- Available: 30 Mbps
- Utilisation: 70%

### Demo 3 — reject an over-capacity request

```text
mininet> h3 python3 <PROJECT_PATH>/client.py reserve --bandwidth 40 --duration 120
```

Expected: rejected, because only 30 Mbps remains available. The existing reservations should remain active.

### Demo 4 — prove that the SDN switch received policy rules

```text
mininet> sh ovs-vsctl list QoS
mininet> sh ovs-vsctl list Queue
mininet> sh ovs-ofctl -O OpenFlow13 dump-flows s1
```

Look for QoS/Queue entries and OpenFlow rules matching client source IPs `10.0.0.1`, `10.0.0.2`, `10.0.0.3` and server destination `10.0.0.4`. Reserved client flows should select queue 1, 2 or 3.

### Demo 5 — release a reservation

Use the actual ID returned by Demo 1 in place of `R-PASTE-ID-HERE`:

```text
mininet> h1 python3 <PROJECT_PATH>/client.py release --reservation-id R-PASTE-ID-HERE
mininet> h2 python3 <PROJECT_PATH>/client.py status
```

Expected: h1's reservation is released and available capacity increases by 30 Mbps.

### Demo 6 — show automatic expiry

```text
mininet> h3 python3 <PROJECT_PATH>/client.py reserve --bandwidth 10 --duration 5
mininet> h1 python3 <PROJECT_PATH>/client.py status
```

Wait at least 6 seconds, then run status again:

```text
mininet> h1 python3 <PROJECT_PATH>/client.py status
```

Expected: the 10 Mbps reservation expires and the capacity becomes available again.

## 8. Optional stronger demonstration — actual traffic shaping

This takes more time but is a good way to show that the controller changes network behaviour, not just the server's reservation table.

Start an iperf3 server on h4:

```text
mininet> h4 iperf3 -s -D
```

Run a baseline test from h1:

```text
mininet> h1 iperf3 -c 10.0.0.4 -t 10
```

Reserve 10 Mbps for h1:

```text
mininet> h1 python3 <PROJECT_PATH>/client.py reserve --bandwidth 10 --duration 120
```

Repeat the throughput test:

```text
mininet> h1 iperf3 -c 10.0.0.4 -t 10
```

The reserved h1 traffic should be shaped by its 10 Mbps queue. Record the actual throughput values printed by iperf3; results can vary with VM resources. Do not write invented measurements into the report.

## 9. Optional concurrency demonstration

Run three 40 Mbps reservations close together:

```text
mininet> h1 python3 <PROJECT_PATH>/client.py reserve --bandwidth 40 --duration 120 &
mininet> h2 python3 <PROJECT_PATH>/client.py reserve --bandwidth 40 --duration 120 &
mininet> h3 python3 <PROJECT_PATH>/client.py reserve --bandwidth 40 --duration 120 &
mininet> h1 python3 <PROJECT_PATH>/client.py status
```

The order of the responses can vary. The key result is that accepted reservations together must never exceed 100 Mbps. The reservation manager uses a lock around the capacity check and update to prevent overbooking.

## 10. Stop and clean up

1. At the `mininet>` prompt, type:

```text
exit
```

2. In Terminal 1, stop the controller with `Ctrl+C`.
3. From a normal Ubuntu terminal in the project folder, run:

```bash
./scripts/cleanup.sh
```

## 11. Optional: run the included logic tests

These tests do not require Mininet or a live controller. They test the reservation manager using a fake controller:

```bash
python3 -m unittest discover -s tests -v
```

Expected: all six tests pass.


