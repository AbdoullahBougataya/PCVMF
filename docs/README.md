# PCVMF documentation

Documentation for **PCVMF 0.3.0**, the Linux-first Python framework for independently scheduled vision, controller, and sensor processes. Begin with the tutorials if this is your first application; use the other sections when you have a specific task or question.

The organization follows [Diátaxis](https://diataxis.fr/): learning through tutorials, accomplishing tasks through how-to guides, looking up facts in reference material, and understanding design decisions through explanation.

| Your goal | Start here |
|---|---|
| Run the framework for the first time | [Your first application](tutorials/first-application.md) |
| Build an algorithm in your own package | [Your first vision plugin](tutorials/vision-plugin.md) |
| Connect more than one data source | [Combine vision and temperature](tutorials/multiple-sensors.md) |
| Use a webcam or recorded video | [Change the frame source](how-to/camera-and-video.md) |
| Write, test, and distribute an extension | [How-to guides](how-to/README.md) |
| Find exact defaults, types, and methods | [Reference](reference/README.md) |
| Understand timing, delivery, and shutdown | [Explanation](explanation/README.md) |
| Upgrade an existing 0.2 application | [Migrate to 0.3](how-to/migrate-to-0.3.md) |
| Diagnose a failure | [Troubleshooting](how-to/troubleshooting.md) |

## Before you begin

The runnable walkthroughs assume a repository checkout on Linux, Python 3.10–3.12, and `uv`. Commands run from the **repository root**, unless a step explicitly changes directory. Python plugins must be installed in the environment used to launch PCVMF. No camera or graphical session is needed for the tutorials.

For a pip-based environment, use the [README's pip setup](../README.md#using-pip-instead-of-uv). With that environment activated, replace `uv run --no-sync pcvmf ...` with `pcvmf ...` and use `python -m pip` to install plugins.

The tutorials use `uv sync --frozen --extra dev` for initial setup. After installing a separate plugin package, use `uv run --no-sync` so automatic synchronization does not remove that package. Repeat its installation if you later synchronize the environment.

PCVMF provides best-effort scheduling and PUB/SUB delivery. It does not guarantee hard real-time deadlines or reliable message delivery. The examples do not operate actuators.

## Browse by documentation type

- [Tutorials](tutorials/README.md): complete a guided exercise and observe its result.
- [How-to guides](how-to/README.md): solve a particular development or operational problem.
- [Reference](reference/README.md): consult exact configuration fields, contracts, and wire formats.
- [Explanation](explanation/README.md): understand the architecture and its tradeoffs.

## Keeping the documentation accurate

This documentation describes the implemented API, not planned features. Source links in the reference identify the corresponding implementation. Update reference defaults when changing code, then check affected walkthroughs. Keep working examples in tutorials and recipes; keep design rationale in explanation pages. The older `docs/` paths point to this documentation for existing bookmarks.
