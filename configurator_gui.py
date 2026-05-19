import json
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


FIELD_SPECS = [
    ("base_url", "Base URL", "POS endpoint, usually keep default."),
    ("token", "Token", "Copy the value after request header `token:`."),
    ("cookie", "Cookie", "Copy the full string after request header `Cookie:`."),
    ("saleorg_id", "Sale Org ID", "Usually keep 11371502 unless your org is different."),
    ("run_mode", "Run Mode", "auto: continue state, backfill: force date range, daily: one day."),
    ("storage_backend", "Storage Backend", "Recommended: mysql"),
    ("agg_item", "Shop Summary agg_item", "Controls summary chain only. Recommended: shop"),
    ("fetch_shop_summary", "Fetch Shop Summary", "true/false. Disable to speed up item-only backfill."),
    ("fetch_item_detail", "Fetch Item Detail", "true/false. Keep true for barcode-level detail."),
    ("mysql_host", "MySQL Host", "Usually 127.0.0.1"),
    ("mysql_port", "MySQL Port", "Usually 3306"),
    ("mysql_user", "MySQL User", "Usually root"),
    ("mysql_password", "MySQL Password", "Your real MySQL password"),
    ("mysql_database", "MySQL Database", "Recommended: pos_ods"),
    ("history_start_date", "History Start", "Format: YYYYMMDD, for example 20220101"),
    ("history_end_date", "History End", "Leave empty to run until latest available date"),
    ("daily_lag_days", "Daily Lag Days", "daily mode runs today minus this value."),
    ("max_days_per_run", "Max Days Per Run", "Recommended: 7 for safety"),
    ("shop_parallel_workers", "Parallel Shops", "Usually 6-8 is enough"),
    ("validate_min_rows_per_shop", "Validate Min Rows", "For validation mode threshold"),
    ("validate_pass_ratio", "Validate Pass Ratio", "For example 0.9 means 90%"),
    ("state_path", "State File", "Incremental sync state JSON path"),
]


DEFAULT_CONFIG = {
    "base_url": "http://sdycpos.sd.yc",
    "token": "",
    "cookie": "",
    "saleorg_id": "11371502",
    "run_mode": "auto",
    "timeout": 30,
    "shop_page_limit": 200,
    "data_page_limit": 500,
    "storage_backend": "mysql",
    "agg_item": "shop",
    "fetch_shop_summary": True,
    "fetch_item_detail": True,
    "shop_parallel_workers": 8,
    "commit_every_n_shops": 50,
    "shop_query_type": "02",
    "validate_min_rows_per_shop": 150,
    "validate_pass_ratio": 0.9,
    "history_start_date": "20220101",
    "history_end_date": "",
    "daily_lag_days": 1,
    "max_days_per_run": 7,
    "sqlite_path": "F:/Data/ods_customer_item_daily.sqlite",
    "mysql_host": "127.0.0.1",
    "mysql_port": 3306,
    "mysql_user": "root",
    "mysql_password": "",
    "mysql_database": "pos_ods",
    "mysql_charset": "utf8mb4",
    "mysql_connect_timeout": 10,
    "state_path": "F:/Data/sync_state.json",
}

INT_FIELDS = {
    "mysql_port",
    "daily_lag_days",
    "max_days_per_run",
    "shop_parallel_workers",
    "validate_min_rows_per_shop",
}

FLOAT_FIELDS = {"validate_pass_ratio"}
BOOL_FIELDS = {"fetch_shop_summary", "fetch_item_detail"}


def get_runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


class ConfiguratorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("POS Dual-Fact Configurator")
        self.root.geometry("1080x780")
        self.root.minsize(960, 720)

        self.app_dir = get_runtime_dir()
        self.default_config_path = self.app_dir / "config.json"
        self.config_path = self.default_config_path
        self.entries = {}
        self._build_ui()
        self.load_config()

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=12)
        top.pack(fill="x")

        ttk.Label(
            top,
            text="POS Dual-Fact Configurator",
            font=("Microsoft YaHei UI", 16, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            top,
            text=(
                "Use this window to fill token, cookie, and MySQL settings. "
                "The Save button writes back to the config.json next to this EXE."
            ),
        ).pack(anchor="w", pady=(4, 8))

        path_row = ttk.Frame(top)
        path_row.pack(fill="x", pady=(4, 10))
        ttk.Label(path_row, text="Current config file:").pack(side="left")
        self.path_var = tk.StringVar()
        ttk.Entry(path_row, textvariable=self.path_var, state="readonly").pack(
            side="left",
            fill="x",
            expand=True,
            padx=8,
        )
        ttk.Button(path_row, text="Choose Config", command=self.choose_config).pack(side="left")
        ttk.Button(path_row, text="Reset To EXE Config", command=self.reset_to_default_config).pack(side="left", padx=(8, 0))

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=12, pady=8)

        config_tab = ttk.Frame(notebook, padding=12)
        help_tab = ttk.Frame(notebook, padding=12)
        notebook.add(config_tab, text="Config")
        notebook.add(help_tab, text="Help")

        canvas = tk.Canvas(config_tab, highlightthickness=0)
        scroll = ttk.Scrollbar(config_tab, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        for row, (key, label, tip) in enumerate(FIELD_SPECS):
            ttk.Label(inner, text=label).grid(row=row, column=0, sticky="nw", padx=(0, 12), pady=8)
            if key == "cookie":
                widget = tk.Text(inner, height=4, width=90, wrap="word")
                widget.grid(row=row, column=1, sticky="ew", pady=8)
                self.entries[key] = widget
            elif key == "run_mode":
                var = tk.StringVar()
                widget = ttk.Combobox(inner, textvariable=var, values=("auto", "backfill", "daily"), state="readonly", width=88)
                widget.grid(row=row, column=1, sticky="ew", pady=8)
                self.entries[key] = var
            elif key == "storage_backend":
                var = tk.StringVar()
                widget = ttk.Combobox(inner, textvariable=var, values=("mysql", "sqlite"), state="readonly", width=88)
                widget.grid(row=row, column=1, sticky="ew", pady=8)
                self.entries[key] = var
            elif key in BOOL_FIELDS:
                var = tk.StringVar()
                widget = ttk.Combobox(inner, textvariable=var, values=("true", "false"), state="readonly", width=88)
                widget.grid(row=row, column=1, sticky="ew", pady=8)
                self.entries[key] = var
            else:
                var = tk.StringVar()
                widget = ttk.Entry(
                    inner,
                    textvariable=var,
                    width=90,
                    show="*" if "password" in key else "",
                )
                widget.grid(row=row, column=1, sticky="ew", pady=8)
                self.entries[key] = var
            ttk.Label(inner, text=tip, foreground="#666666").grid(row=row, column=2, sticky="nw", pady=8)

        inner.columnconfigure(1, weight=1)

        action_bar = ttk.Frame(self.root, padding=12)
        action_bar.pack(fill="x")
        ttk.Button(action_bar, text="Reload", command=self.load_config).pack(side="left")
        ttk.Button(action_bar, text="Save", command=self.save_config).pack(side="left", padx=8)
        ttk.Button(action_bar, text="Open Logs", command=self.open_logs).pack(side="left")
        ttk.Button(action_bar, text="Run Program", command=self.run_program).pack(side="right")

        help_text = tk.Text(help_tab, wrap="word", height=30)
        help_text.pack(fill="both", expand=True)
        help_text.insert(
            "1.0",
            "\n".join(
                [
                    "1. Token: fill the value after request header `token:`.",
                    "2. Cookie: fill the full value after request header `Cookie:`.",
                    "   Example: xsm_client=...; token=...; gray_scale=0",
                    "3. This dual-fact program writes two tables at the same time:",
                    "   - fact_customer_shop_daily: daily shop summary",
                    "   - fact_customer_item_daily: daily item detail",
                    "4. Run Mode:",
                    "   - auto: continue from state_path last_completed_date.",
                    "   - backfill: force history_start_date to history_end_date.",
                    "   - daily: run today - daily_lag_days.",
                    "5. `agg_item` in this config controls the shop summary chain only.",
                    "   Item detail chain is fixed to shop_barcode + day + tenantIds/shopIds.",
                    "6. Save writes to the config.json beside the EXE, not to a temp folder.",
                    "7. After Save, you can click Run Program directly.",
                ]
            ),
        )
        help_text.config(state="disabled")

    def reset_to_default_config(self) -> None:
        self.config_path = self.default_config_path
        self.load_config()

    def choose_config(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose config.json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            initialdir=str(self.app_dir),
        )
        if path:
            self.config_path = Path(path)
            self.load_config()

    def _get_widget_value(self, key: str) -> str:
        widget = self.entries[key]
        if isinstance(widget, tk.Text):
            return widget.get("1.0", "end").strip()
        return widget.get().strip()

    def _set_widget_value(self, key: str, value: str) -> None:
        widget = self.entries[key]
        if isinstance(widget, tk.Text):
            widget.delete("1.0", "end")
            widget.insert("1.0", value)
        else:
            widget.set(value)

    def load_config(self) -> None:
        data = dict(DEFAULT_CONFIG)
        if self.config_path.exists():
            try:
                loaded = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
                if isinstance(loaded, dict):
                    data.update(loaded)
            except Exception as exc:
                messagebox.showerror("Load Failed", f"Could not read config:\n{exc}")
                return

        self.path_var.set(str(self.config_path))
        for key, _, _ in FIELD_SPECS:
            self._set_widget_value(key, str(data.get(key, "")))

    def save_config(self) -> None:
        data = dict(DEFAULT_CONFIG)
        for key, _, _ in FIELD_SPECS:
            raw_value = self._get_widget_value(key)
            if key in INT_FIELDS:
                data[key] = int(raw_value or 0)
            elif key in FLOAT_FIELDS:
                data[key] = float(raw_value or 0)
            elif key in BOOL_FIELDS:
                data[key] = str(raw_value).strip().lower() in {"1", "true", "yes", "y"}
            else:
                data[key] = raw_value

        target_path = self.config_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.path_var.set(str(target_path))
        messagebox.showinfo("Saved", f"Config saved to:\n{target_path}")

    def open_logs(self) -> None:
        log_dir = self.app_dir / "logs"
        log_dir.mkdir(exist_ok=True)
        subprocess.Popen(["explorer", str(log_dir)])

    def run_program(self) -> None:
        run_bat = self.app_dir / "run_once.bat"
        if not run_bat.exists():
            messagebox.showerror("Run Failed", f"run_once.bat not found:\n{run_bat}")
            return
        subprocess.Popen(["cmd", "/c", str(run_bat)], cwd=str(self.app_dir))


def main() -> None:
    root = tk.Tk()
    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    ConfiguratorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
