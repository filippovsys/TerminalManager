# -*- coding: utf-8 -*-
"""Диалог ремонта: отправить / вернуть / прошить.
Позволяет редактировать любой ремонт терминала или создавать новый."""

import re
import tkinter as tk
from datetime import date
from tkinter import ttk, messagebox

import database
from gui import utils


def parse_date(s):
    """YYYY-MM-DD или DD.MM.YYYY -> YYYY-MM-DD. Иначе как есть."""
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return s


class RepairDialog(tk.Toplevel):
    def __init__(self, master, user, terminal_id, repair_id=None):
        super().__init__(master)
        self.user = user
        self.terminal_id = terminal_id
        self.repair_id = repair_id
        self.result = False
        self.existing = None  # текущий dict из БД

        self.title("Ремонт терминала")
        self.resizable(False, False)

        # Если repair_id не задан -- ищем активный ремонт
        if self.repair_id is None:
            with database.get_connection() as conn:
                row = conn.execute(
                    "SELECT id FROM terminal_repairs "
                    "WHERE terminal_id = ? AND returned_at IS NULL "
                    "ORDER BY id DESC LIMIT 1",
                    (terminal_id,),
                ).fetchone()
            if row:
                self.repair_id = row["id"]

        self._build()
        utils.apply_to_all_entries(self)
        self._load()

        self.transient(master)
        self.grab_set()
        self.wait_window(self)

    def _build(self):
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        # Заголовок статуса
        self.status_label = ttk.Label(outer, text="", font=("TkDefaultFont", 10, "bold"))
        self.status_label.pack(anchor="w", pady=(0, 8))

        # Причина
        reason_frame = ttk.LabelFrame(outer, text="Причина неисправности", padding=8)
        reason_frame.pack(fill="x", pady=(0, 8))
        self.reason_var = tk.StringVar()
        ttk.Entry(reason_frame, textvariable=self.reason_var, width=60).pack(fill="x")

        # Даты
        dates = ttk.LabelFrame(outer, text="Даты", padding=8)
        dates.pack(fill="x", pady=(0, 8))

        self.reported_var = tk.StringVar()
        self.sent_var = tk.StringVar()
        self.returned_var = tk.StringVar()
        self.firmware_var = tk.StringVar()

        ttk.Label(dates, text="Сообщено:").grid(row=0, column=0, sticky="w")
        ttk.Entry(dates, textvariable=self.reported_var, width=14).grid(row=0, column=1, sticky="w", padx=(4, 0))
        ttk.Label(dates, text="(ГГГГ-ММ-ДД)", foreground="gray").grid(row=0, column=2, sticky="w", padx=(6, 0))

        ttk.Label(dates, text="Отправлен:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(dates, textvariable=self.sent_var, width=14).grid(row=1, column=1, sticky="w", padx=(4, 0), pady=(4, 0))
        ttk.Button(dates, text="Отправить сегодня", command=self._set_sent_today).grid(
            row=1, column=2, sticky="w", padx=(6, 0), pady=(4, 0))

        ttk.Label(dates, text="Вернулся:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(dates, textvariable=self.returned_var, width=14).grid(row=2, column=1, sticky="w", padx=(4, 0), pady=(4, 0))
        ttk.Button(dates, text="Вернулся сегодня", command=self._set_returned_today).grid(
            row=2, column=2, sticky="w", padx=(6, 0), pady=(4, 0))

        ttk.Label(dates, text="Прошит:").grid(row=3, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(dates, textvariable=self.firmware_var, width=14).grid(row=3, column=1, sticky="w", padx=(4, 0), pady=(4, 0))
        ttk.Button(dates, text="Прошит сегодня", command=self._set_firmware_today).grid(
            row=3, column=2, sticky="w", padx=(6, 0), pady=(4, 0))

        # Результат и комментарий
        res_frame = ttk.LabelFrame(outer, text="Результат", padding=8)
        res_frame.pack(fill="x", pady=(0, 8))
        self.result_var = tk.StringVar()
        ttk.Entry(res_frame, textvariable=self.result_var, width=60).pack(fill="x")

        com_frame = ttk.LabelFrame(outer, text="Комментарий", padding=8)
        com_frame.pack(fill="x", pady=(0, 8))
        self.comment_var = tk.StringVar()
        ttk.Entry(com_frame, textvariable=self.comment_var, width=60).pack(fill="x")

        # Кнопки
        btns = ttk.Frame(outer)
        btns.pack(fill="x")
        ttk.Button(btns, text="Сохранить", command=self._save).pack(side="right", padx=2)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="right", padx=2)

    # ------------------------------------------------------------------
    def _set_sent_today(self):
        self.sent_var.set(date.today().isoformat())

    def _set_returned_today(self):
        self.returned_var.set(date.today().isoformat())

    def _set_firmware_today(self):
        self.firmware_var.set(date.today().isoformat())

    def _load(self):
        with database.get_connection() as conn:
            if self.repair_id:
                row = conn.execute(
                    "SELECT * FROM terminal_repairs WHERE id = ?", (self.repair_id,)
                ).fetchone()
                if row is None:
                    messagebox.showerror("Ошибка", "Ремонт не найден", parent=self)
                    self.destroy()
                    return
                self.existing = dict(row)
                self.reason_var.set(row["reason"] or "")
                self.reported_var.set(row["reported_at"] or "")
                self.sent_var.set(row["sent_at"] or "")
                self.returned_var.set(row["returned_at"] or "")
                self.firmware_var.set(row["firmware_at"] or "")
                self.result_var.set(row["result"] or "")
                self.comment_var.set(row["comment"] or "")
                self.status_label.config(text="Существующий ремонт (редактирование)")
            else:
                self.existing = None
                self.reason_var.set("")
                self.reported_var.set(date.today().isoformat())
                self.sent_var.set("")
                self.returned_var.set("")
                self.firmware_var.set("")
                self.result_var.set("")
                self.comment_var.set("")
                self.status_label.config(text="Новый ремонт")

    def _save(self):
        reason = self.reason_var.get().strip() or None
        reported = parse_date(self.reported_var.get())
        sent = parse_date(self.sent_var.get())
        returned = parse_date(self.returned_var.get())
        firmware = parse_date(self.firmware_var.get())
        result = self.result_var.get().strip() or None
        comment = self.comment_var.get().strip() or None

        if not self.existing and not reason and not sent:
            messagebox.showerror(
                "Ошибка",
                "Укажите хотя бы причину или дату отправки (иначе это не ремонт).",
                parent=self,
            )
            return

        try:
            with database.get_connection() as conn:
                if self.existing is None:
                    # Создаём новый ремонт
                    new_id = database.create_repair(
                        conn, self.terminal_id, reason or "—", self.user["id"],
                        reported_at=reported, sent_at=sent,
                    )
                    self.repair_id = new_id
                    # Обновляем остальные поля (result/comment/firmware/returned)
                    database.update_repair(
                        conn, new_id, self.user["id"],
                        returned_at=returned,
                        firmware_at=firmware,
                        result=result,
                        comment=comment,
                    )
                    # Если отправлен -- перемещаем в мастерскую
                    if sent:
                        database.move_terminal(
                            conn, self.terminal_id, "repair_shop", self.user["id"],
                            comment=f"ремонт: {reason or '—'}",
                        )
                    # Если вернулся, но НЕ прошит -- на склад
                    if returned and not firmware:
                        database.move_terminal(
                            conn, self.terminal_id, "warehouse", self.user["id"],
                            comment="вернулся из ремонта, ждёт прошивку",
                        )
                    # Если прошит -- на склад (пользователь потом сам переместит)
                    if firmware:
                        database.move_terminal(
                            conn, self.terminal_id, "warehouse", self.user["id"],
                            comment="прошит после ремонта",
                        )
                else:
                    was_returned = self.existing["returned_at"]
                    was_firmware = self.existing["firmware_at"]

                    database.update_repair(
                        conn, self.repair_id, self.user["id"],
                        reason=reason,
                        reported_at=reported,
                        sent_at=sent,
                        returned_at=returned,
                        firmware_at=firmware,
                        result=result,
                        comment=comment,
                    )

                    # Если дата возврата только что появилась -- на склад
                    if returned and not was_returned:
                        database.move_terminal(
                            conn, self.terminal_id, "warehouse", self.user["id"],
                            comment="вернулся из ремонта",
                        )
                    # Если дата прошивки только что появилась -- на склад (потом сами перенесут)
                    if firmware and not was_firmware:
                        database.move_terminal(
                            conn, self.terminal_id, "warehouse", self.user["id"],
                            comment="прошит после ремонта",
                        )
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return

        self.result = True
        messagebox.showinfo("Готово", "Ремонт сохранён", parent=self)
        self.destroy()