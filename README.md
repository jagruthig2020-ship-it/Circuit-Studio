# CIRCUIT STUDIO

**A workbench for people who want to build circuits, not just copy diagrams.**

I kept running into the same problem while working with ESP32s: I'd finish wiring something, it wouldn't respond, and I'd spend the next half hour checking pins and jumper wires again. During one of my builds, ASTRA, that became a particularly frustrating part of the process. I wanted a better starting point for myself and for someone opening their first box of sensors.

That's where CIRCUIT STUDIO came from.

The idea is to keep the process in one place: describe what you want to make, figure out what you actually need to buy, understand the components, plan connections, photograph the build, and troubleshoot what the board really reports.

## What you can try

- **Plan:** Describe a project and get a starter component list, with owned vs. needed parts and a reference wiring plan.
- **Components:** Explore hardware and its purpose before buying or wiring it.
- **Wire:** Review pin-level connections and try simulated mistakes, like swapping I²C SDA and SCL or forgetting a common ground.
- **Inspect:** Upload a real circuit photo, highlight possible jumper-wire segments, identify candidate component regions, and annotate endpoints against the plan.
- **Live Bench:** Work with ESP32 serial diagnostics and distinguish real device output from simulated or unverified results.
- **Ask:** Troubleshoot in the context of the current project, using the local backend.

The photo tools are **not** a magic circuit tester: colored-line detection can mistake edges for wires, and endpoint identification still needs human confirmation. A photograph cannot prove electrical continuity. Live hardware checks depend on compatible ESP32 firmware and correct wiring.

## Running locally

On Windows, from the project folder:

```powershell
py -m pip install -r backend\requirements.txt
.\START_CIRCUIT_STUDIO.bat
```

Open **http://127.0.0.1:8000/** in Chrome or Edge. The app uses a Python/FastAPI backend; there is no npm setup required.

For actual board diagnostics, flash the sketch in `firmware/CircuitStudioDiagnostics/` using Arduino IDE. Check its pin definitions against your hardware. Close Arduino Serial Monitor before connecting through the website because the serial port cannot normally be opened by both at once.

The included backend tests can be run with:

```powershell
py -m pytest backend\tests -q
```

## A circuit I use to test it

An **ESP32 DevKit V1 + MPU6050** movement monitor, with a push button and an active buzzer. The reference I²C pins are SDA **GPIO21** and SCL **GPIO22**; the bundled diagnostic sketch uses **GPIO25** for the button and **GPIO26** for buzzer control. Power, buzzer driver, and module logic-level compatibility must be checked for the actual parts.

The useful test isn't whether the page can draw a circuit. It's whether I can change the plan, catch a mismatch, and explain what a serial message such as `imu:false` does and **doesn't** tell me.

## Where I want to take it

I'd like Inspect to identify more component pins and trace visible wire endpoints with higher confidence, and eventually connect this to safe physical continuity measurements. Those are in-progress directions, **not features I claim are already solved**.

Built as an ongoing personal project for learning, experimenting, and making electronics feel less intimidating.
