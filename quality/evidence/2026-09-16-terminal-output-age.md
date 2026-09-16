# Selected terminal output-age correction

## Natural failure

The selected terminal rendered the task name and last-output age with an inner CSS Grid. The age was computed only when task polling happened, so a quiet task could remain frozen at one value. Minute-scale values were rounded down to a single `m`, hiding the seconds that matter while watching a recently quiet process.

## Contract

- The task name and age share one non-wrapping flex row; the complete terminal header remains at most 52 px high.
- Actual log metadata remains the source of truth. One mounted timer recomputes wall-clock age every second and is cleaned up on unmount.
- Ages below 5 seconds render nothing. Values use `Ns`, `Nm Ns`, `Nh Nm`, and `Nd Nh`.
- Terminal rail rows, output-less tasks, and completed history never render the age.

## Machine oracle

The Edge journey touches the selected task's real `output.log` mtime, requires the age to remain absent inside the threshold, then requires it to appear and advance without a server write. It rewinds the real mtime by 127 seconds and requires `2m Ns`. Bounding boxes prove task name and age centers differ by at most 3 px (their font sizes differ), the age is to the right, and the header is no taller than 52 px. Existing million-line tail-window and chunked-search gates remain mandatory.

The failure mutant is any implementation that stacks the fields, freezes the derived value until polling, displays below threshold, reduces a minute-scale age to minutes only, or renders the timer for history/no-output terminals.
