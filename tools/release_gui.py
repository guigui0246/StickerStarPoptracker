"""Small graphical launcher for the bundled CLI and APWorld installer."""

from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def cli_command() -> list[str]:
    if not getattr(sys, "frozen", False):
        return [sys.executable, "-m", "tools.release_cli"]
    bundle = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "bundled"
    return [str(bundle / ("cli_randomizer.exe" if sys.platform == "win32" else "cli_randomizer"))]


def main() -> None:
    root = tk.Tk()
    root.title("Sticker Star Randomizer")
    root.geometry("760x480")
    bundle = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "bundled"
    command = tk.StringVar(value="generate")
    arguments = tk.StringVar()
    ttk.Label(root, text="Existing tools: generation uses a logic catalog; sticker patching is experimental.").pack(pady=12)
    ttk.Combobox(
        root, textvariable=command, values=("generate", "patch", "track", "client", "catalog"), state="readonly"
    ).pack()
    ttk.Label(root, text="Command arguments (quote paths with spaces); use --help for available options.").pack(pady=8)
    ttk.Entry(root, textvariable=arguments, width=100).pack(padx=12, fill="x")
    output = tk.Text(root, wrap="word", state="disabled")

    def display(text: str) -> None:
        output.configure(state="normal")
        output.insert("end", text)
        output.see("end")
        output.configure(state="disabled")

    def execute() -> None:
        try:
            values = shlex.split(arguments.get())
        except ValueError as error:
            messagebox.showerror("Invalid arguments", str(error))
            return
        selected = command.get()
        button.configure(state="disabled")

        def worker() -> None:
            try:
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                with subprocess.Popen(
                    [*cli_command(), selected, *values],
                    cwd=Path(__file__).resolve().parents[1] if not getattr(sys, "frozen", False) else None,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=flags,
                ) as process:
                    if process.stdout is not None:
                        for line in process.stdout:
                            root.after(0, display, line)
                    code = process.wait()
                    root.after(0, display, f"Process exited with code {code}\n")
            except OSError as error:
                root.after(0, display, f"{error}\n")
            finally:
                root.after(0, lambda: button.configure(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def install() -> None:
        selected = filedialog.askdirectory(title="Select your Archipelago installation directory")
        if not selected:
            return
        destination = Path(selected) / "custom_worlds" / "sticker-star.apworld"
        if destination.exists() and not messagebox.askyesno("Replace APWorld", "Replace the installed Sticker Star APWorld?"):
            return
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(bundle / "sticker-star.apworld", destination)
        except OSError as error:
            messagebox.showerror("Installation failed", str(error))
            return
        messagebox.showinfo("APWorld installed", "Restart Archipelago to load the Sticker Star Logic Demo.")

    button = ttk.Button(root, text="Run command", command=execute)
    button.pack(pady=8)
    ttk.Button(root, text="Install APWorld", command=install).pack()
    output.pack(padx=12, pady=12, fill="both", expand=True)
    root.mainloop()


if __name__ == "__main__":
    main()
