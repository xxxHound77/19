from __future__ import annotations

import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from PIL import Image, ImageTk

from db import connect
from import_data import seed

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
LOGO_PATH = ASSETS_DIR / "import" / "icon.jpg"
APP_ICON_ICO = ASSETS_DIR / "import" / "icon.ico"
PLACEHOLDER = ASSETS_DIR / "import" / "picture.png"
IMAGES_DIR = ASSETS_DIR / "images"


_TEMP_ICO_PATH: Optional[Path] = None


def _build_temp_ico() -> Optional[Path]:
    """Создаёт многоразмерный .ico во временной директории с ASCII-путём (исправляет проблемы Tkinter с иконкой в Windows)."""
    global _TEMP_ICO_PATH
    if _TEMP_ICO_PATH and _TEMP_ICO_PATH.exists():
        return _TEMP_ICO_PATH

    src_img = None
    if LOGO_PATH.exists():
        src_img = LOGO_PATH
    else:
        png = APP_ICON_ICO.with_suffix(".png")
        if png.exists():
            src_img = png

    try:
        if src_img is not None:
            img = Image.open(src_img).convert("RGBA")
            sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
            tmp = Path(tempfile.gettempdir()) / "app_icon.ico"
            img.save(tmp, sizes=sizes)
            _TEMP_ICO_PATH = tmp
            return tmp
    except Exception:
        pass

    if APP_ICON_ICO.exists():
        try:
            tmp = Path(tempfile.gettempdir()) / "app_icon_existing.ico"
            tmp.write_bytes(APP_ICON_ICO.read_bytes())
            _TEMP_ICO_PATH = tmp
            return tmp
        except Exception:
            return None
    return None


def set_window_icon(win: tk.Misc) -> None:
    """Устанавливает иконку окна для Tk/Toplevel."""
    ico = _build_temp_ico()
    if ico is not None:
        try:
            win.iconbitmap(str(ico))
            return
        except Exception:
            pass

    try:
        src_img = LOGO_PATH if LOGO_PATH.exists() else PLACEHOLDER
        img = Image.open(src_img).convert("RGBA").resize((32, 32))
        photo = ImageTk.PhotoImage(img)
        setattr(win, "_icon_photo_ref", photo)
        win.iconphoto(True, photo)
    except Exception:
        pass


# Руководство по стилю (Приложение 3)
COLOR_BG_MAIN = "#FFFFFF"
COLOR_BG_EXTRA = "#00FFFF"
COLOR_ACCENT = "#0000FF"
COLOR_DISCOUNT_BIG = "#008080"
COLOR_OUT_OF_STOCK = "#C0C0C0"

FONT_FAMILY = "Calibri"


@dataclass
class Session:
    user_id: Optional[int] = None
    full_name: str = "Гость"
    role: str = "Гость"


def money(v: float) -> str:
    """Форматирует число как денежную сумму с отступами тысяч и двумя знаками после запятой."""
    return f"{v:,.2f}".replace(",", " ")


class ScrollableFrame(ttk.Frame):
    """Контейнер с вертикальной прокруткой для размещения карточек товаров."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, background=COLOR_BG_MAIN)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.inner = ttk.Frame(self.canvas)
        self.inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_inner_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.inner_id, width=event.width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class App(tk.Tk):
    """Главное окно приложения — управляет переключением экранов (авторизация, товары, заказы)."""

    def __init__(self):
        super().__init__()
        self.title("Авторизация")
        self.configure(bg=COLOR_BG_MAIN)
        self.geometry("760x540")
        self.minsize(720, 500)
        self.session = Session()
        set_window_icon(self)
        seed()

        self._frame: Optional[tk.Frame] = None
        self.show_login()

    def _switch(self, frame: tk.Frame, title: str):
        if self._frame is not None:
            self._frame.destroy()
        self._frame = frame
        self._frame.pack(fill="both", expand=True)
        self.title(title)

    def show_login(self):
        self.session = Session()
        self._switch(LoginFrame(self), "Авторизация")

    def show_products(self):
        title = f"Список товаров — {self.session.role}"
        self._switch(ProductListFrame(self), title)

    def show_orders(self):
        title = f"Заказы — {self.session.role}"
        self._switch(OrdersFrame(self), title)


class LoginFrame(tk.Frame):
    """Экран авторизации: ввод логина/пароля или вход в режиме гостя."""

    def __init__(self, master: App):
        super().__init__(master, bg=COLOR_BG_MAIN)
        self.master = master

        wrapper = tk.Frame(self, bg=COLOR_BG_MAIN)
        wrapper.pack(expand=True)

        self.logo_img = self._load_logo(160)
        tk.Label(wrapper, image=self.logo_img, bg=COLOR_BG_MAIN).pack(pady=(20, 10))

        tk.Label(
            wrapper,
            text="Вход в систему",
            font=(FONT_FAMILY, 18, "bold"),
            bg=COLOR_BG_MAIN,
        ).pack(pady=(0, 15))

        form = tk.Frame(wrapper, bg=COLOR_BG_MAIN)
        form.pack(padx=30, pady=10)

        form.grid_columnconfigure(0, weight=1)

        tk.Label(form, text="Логин:", font=(FONT_FAMILY, 12), bg=COLOR_BG_MAIN).grid(row=0, column=0, sticky="w")
        self.login_var = tk.StringVar()
        login_entry = tk.Entry(
            form,
            textvariable=self.login_var,
            font=(FONT_FAMILY, 12),
            width=34,
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground="#999999",
            highlightcolor="#666666",
            bg="white",
        )
        login_entry.grid(row=1, column=0, pady=(0, 12), ipady=4, sticky="ew")
        login_entry.insert(0, "")

        tk.Label(form, text="Пароль:", font=(FONT_FAMILY, 12), bg=COLOR_BG_MAIN).grid(row=2, column=0, sticky="w")
        self.pass_var = tk.StringVar()
        pass_entry = tk.Entry(
            form,
            textvariable=self.pass_var,
            font=(FONT_FAMILY, 12),
            width=34,
            show="*",
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground="#999999",
            highlightcolor="#666666",
            bg="white",
        )
        pass_entry.grid(row=3, column=0, pady=(0, 15), ipady=4, sticky="ew")

        btns = tk.Frame(wrapper, bg=COLOR_BG_MAIN)
        btns.pack(pady=10)

        tk.Button(
            btns,
            text="Войти",
            font=(FONT_FAMILY, 12, "bold"),
            bg=COLOR_ACCENT,
            fg="white",
            relief="flat",
            width=26,
            command=self._login,
        ).pack(pady=(0, 10), ipady=6)

        tk.Button(
            btns,
            text="Войти как гость",
            font=(FONT_FAMILY, 12),
            bg=COLOR_BG_EXTRA,
            relief="flat",
            width=26,
            command=self._guest,
        ).pack(ipady=6)

        login_entry.focus_set()

    def _load_logo(self, size: int) -> ImageTk.PhotoImage:
        path = LOGO_PATH if LOGO_PATH.exists() else None
        if not path:
            img = Image.new("RGB", (size, size), "white")
        else:
            img = Image.open(path).convert("RGBA")
            img.thumbnail((size, size), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(img)

    def _guest(self):
        self.master.session = Session(user_id=None, full_name="Гость", role="Гость")
        self.master.show_products()

    def _login(self):
        login = self.login_var.get().strip()
        password = self.pass_var.get().strip()
        if not login or not password:
            messagebox.showwarning("Ошибка ввода", "Введите логин и пароль.")
            return

        conn = connect()
        try:
            row = conn.execute(
                """
                SELECT u.UserId, u.FullName, r.RoleName
                FROM Users u
                JOIN Roles r ON r.RoleId = u.RoleId
                WHERE u.Login = ? AND u.Password = ?
                """,
                (login, password),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            messagebox.showerror("Ошибка авторизации", "Неверный логин или пароль. Проверьте данные и попробуйте снова.")
            return

        self.master.session = Session(user_id=int(row["UserId"]), full_name=row["FullName"], role=row["RoleName"])
        self.master.show_products()


class ProductListFrame(tk.Frame):
    """Список товаров с карточками, фильтрацией, сортировкой и поиском (в зависимости от роли)."""

    def __init__(self, master: App):
        super().__init__(master, bg=COLOR_BG_MAIN)
        self.master = master
        self._card_images: List[ImageTk.PhotoImage] = []
        self._edit_window: Optional[tk.Toplevel] = None

        header = tk.Frame(self, bg=COLOR_BG_EXTRA)
        header.pack(fill="x")

        tk.Label(
            header,
            text=f"Список товаров — {self.master.session.role}",
            font=(FONT_FAMILY, 14, "bold"),
            bg=COLOR_BG_EXTRA,
        ).pack(side="left", padx=12, pady=10)

        right = tk.Frame(header, bg=COLOR_BG_EXTRA)
        right.pack(side="right", padx=12)

        tk.Label(right, text=self.master.session.full_name, font=(FONT_FAMILY, 12, "bold"), bg=COLOR_BG_EXTRA).pack(
            side="left", padx=(0, 10)
        )
        tk.Button(
            right,
            text="Выйти",
            font=(FONT_FAMILY, 11, "bold"),
            bg="#FF6B6B",
            fg="white",
            relief="flat",
            command=self.master.show_login,
        ).pack(side="left", pady=6)

        controls = tk.Frame(self, bg=COLOR_BG_MAIN)
        controls.pack(fill="x", padx=12, pady=(10, 4))

        self.search_var = tk.StringVar()
        self.discount_var = tk.StringVar(value="Все диапазоны")
        self.sort_field = tk.StringVar(value="Цена")
        self.sort_asc = tk.BooleanVar(value=True)

        self.role = self.master.session.role
        self.can_filter = self.role in ("Менеджер", "Администратор")
        self.can_edit = self.role == "Администратор"
        self.can_orders = self.role in ("Менеджер", "Администратор")

        if self.can_filter:
            tk.Label(controls, text="Поиск:", font=(FONT_FAMILY, 12), bg=COLOR_BG_MAIN).pack(side="left")
            search_entry = tk.Entry(controls, textvariable=self.search_var, font=(FONT_FAMILY, 12), width=28)
            search_entry.pack(side="left", padx=(6, 18), ipady=2)

            tk.Label(controls, text="Скидка:", font=(FONT_FAMILY, 12), bg=COLOR_BG_MAIN).pack(side="left")
            self.discount_combo = ttk.Combobox(
                controls, textvariable=self.discount_var, state="readonly", width=26, font=(FONT_FAMILY, 11)
            )
            self.discount_combo["values"] = [
                "Все диапазоны",
                "0 - 10,99%",
                "11 - 14,99%",
                "15% и более",
            ]
            self.discount_combo.current(0)
            self.discount_combo.pack(side="left", padx=(6, 18))

            tk.Label(controls, text="Сортировка:", font=(FONT_FAMILY, 12), bg=COLOR_BG_MAIN).pack(side="left")
            self.sort_field_combo = ttk.Combobox(
                controls, textvariable=self.sort_field, state="readonly", width=18, font=(FONT_FAMILY, 11)
            )
            self.sort_field_combo["values"] = ["Цена", "Кол-во на складе"]
            self.sort_field_combo.current(0)
            self.sort_field_combo.pack(side="left", padx=(6, 6))

            sort_btn = tk.Button(
                controls,
                text="▲",
                font=(FONT_FAMILY, 11, "bold"),
                bg=COLOR_BG_EXTRA,
                relief="flat",
                command=self._toggle_sort,
            )
            sort_btn.pack(side="left")
            self.sort_btn = sort_btn

            self.search_var.trace_add("write", lambda *_: self.refresh())
            self.discount_var.trace_add("write", lambda *_: self.refresh())
            self.sort_field.trace_add("write", lambda *_: self.refresh())
        else:
            tk.Label(
                controls,
                font=(FONT_FAMILY, 11),
                bg=COLOR_BG_MAIN,
            ).pack(side="left")

        actions = tk.Frame(self, bg=COLOR_BG_MAIN)
        actions.pack(fill="x", padx=12, pady=(2, 8))

        if self.can_edit:
            tk.Button(
                actions,
                text="+ Добавить товар",
                font=(FONT_FAMILY, 11),
                bg=COLOR_ACCENT,
                fg="white",
                relief="flat",
                command=self._add_product,
            ).pack(side="left", padx=(0, 10), ipady=2)

            tk.Button(
                actions,
                text="Редактировать",
                font=(FONT_FAMILY, 11),
                bg=COLOR_BG_EXTRA,
                relief="flat",
                command=self._edit_selected,
            ).pack(side="left", padx=(0, 10), ipady=2)

            tk.Button(
                actions,
                text="Удалить",
                font=(FONT_FAMILY, 11),
                bg="#FF6B6B",
                fg="white",
                relief="flat",
                command=self._delete_selected,
            ).pack(side="left", padx=(0, 10), ipady=2)

        if self.can_orders:
            tk.Button(
                actions,
                text="Просмотр заказов",
                font=(FONT_FAMILY, 11),
                bg=COLOR_BG_MAIN,
                relief="groove",
                command=self.master.show_orders,
            ).pack(side="left", ipady=2)

        self.list_area = ScrollableFrame(self)
        self.list_area.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.selected_product_id: Optional[int] = None

        self.refresh()

    def _toggle_sort(self):
        # Переключаем направление сортировки и обновляем текст кнопки
        self.sort_asc.set(not self.sort_asc.get())
        self.sort_btn.configure(text="▲" if self.sort_asc.get() else "▼")
        self.refresh()

    def _query_products(self) -> List[sqlite3.Row]:
        # Динамически собираем SQL: фильтры по поиску, скидке и сортировка
        conn = connect()
        try:
            base = (
                """
                SELECT
                    p.ProductId, p.Article, p.ProductName, p.Description, p.Price, p.DiscountPercent, p.StockQty,
                    p.PhotoPath,
                    c.CategoryName,
                    m.ManufacturerName,
                    s.SupplierName,
                    u.UnitName
                FROM Products p
                JOIN Categories c ON c.CategoryId = p.CategoryId
                JOIN Manufacturers m ON m.ManufacturerId = p.ManufacturerId
                JOIN Suppliers s ON s.SupplierId = p.SupplierId
                JOIN Units u ON u.UnitId = p.UnitId
                """
            )
            where = []
            params: List[Any] = []

            if self.can_filter:
                q = self.search_var.get().strip()
                if q:
                    like = f"%{q}%"
                    # Поиск по семи текстовым полям одновременно
                    where.append(
                        "(p.Article LIKE ? OR p.ProductName LIKE ? OR p.Description LIKE ? OR c.CategoryName LIKE ? OR "
                        "m.ManufacturerName LIKE ? OR s.SupplierName LIKE ? OR u.UnitName LIKE ?)"
                    )
                    params += [like] * 7

                disc = self.discount_var.get().strip()
                if disc == "0 - 10,99%":
                    where.append("p.DiscountPercent BETWEEN 0 AND 10.99")
                elif disc == "11 - 14,99%":
                    where.append("p.DiscountPercent BETWEEN 11 AND 14.99")
                elif disc == "15% и более":
                    where.append("p.DiscountPercent >= 15")

            if where:
                base += " WHERE " + " AND ".join(where)

            sort_col = "p.Price" if self.sort_field.get() == "Цена" else "p.StockQty"
            base += f" ORDER BY {sort_col} " + ("ASC" if self.sort_asc.get() else "DESC")

            rows = conn.execute(base, params).fetchall()
            return rows
        finally:
            conn.close()

    def refresh(self):
        for w in self.list_area.inner.winfo_children():
            w.destroy()
        self._card_images.clear()
        self.selected_product_id = None

        rows = self._query_products()
        for r in rows:
            self._create_card(r)

    def _load_product_image(self, rel_path: Optional[str]) -> ImageTk.PhotoImage:
        path = None
        if rel_path:
            p = BASE_DIR / rel_path
            if p.exists():
                path = p
        if path is None:
            path = PLACEHOLDER

        img = Image.open(path).convert("RGBA")
        img.thumbnail((120, 90), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(img)

    def _card_bg(self, discount: float, stock: int) -> str:
        # Возвращает цвет фона карточки: серый если нет на складе,
        # бирюзовый если скидка от 15%, иначе белый
        if stock <= 0:
            return COLOR_OUT_OF_STOCK
        if discount >= 15:
            return COLOR_DISCOUNT_BIG
        return COLOR_BG_MAIN

    def _create_card(self, r: sqlite3.Row):
        bg = self._card_bg(float(r["DiscountPercent"]), int(r["StockQty"]))

        card = tk.Frame(self.list_area.inner, bg=bg, bd=1, relief="solid")
        card.pack(fill="x", pady=8)
        card.bind("<Button-1>", lambda e, pid=int(r["ProductId"]): self._select(pid))
        if self.can_edit:
            card.bind("<Double-Button-1>", lambda e, pid=int(r["ProductId"]): self._open_edit(pid))

        img = self._load_product_image(r["PhotoPath"])
        self._card_images.append(img)
        img_lbl = tk.Label(card, image=img, bg=bg)
        img_lbl.grid(row=0, column=0, rowspan=6, padx=10, pady=10, sticky="n")
        img_lbl.bind("<Button-1>", lambda e, pid=int(r["ProductId"]): self._select(pid))

        title = f"{r['CategoryName']}  |  {r['ProductName']}"
        tk.Label(card, text=title, font=(FONT_FAMILY, 13, "bold"), bg=bg).grid(row=0, column=1, sticky="w", padx=8, pady=(10, 2))

        def row(label: str, value: str, rr: int):
            tk.Label(card, text=label, font=(FONT_FAMILY, 11, "bold"), bg=bg).grid(row=rr, column=1, sticky="w", padx=8)
            tk.Label(card, text=value, font=(FONT_FAMILY, 11), bg=bg, wraplength=420, justify="left").grid(
                row=rr, column=2, sticky="w", padx=8
            )

        row("Описание:", str(r["Description"] or ""), 1)
        row("Производитель:", str(r["ManufacturerName"]), 2)
        row("Поставщик:", str(r["SupplierName"]), 3)
        row("Единица измерения:", str(r["UnitName"]), 4)
        row("Количество на складе:", str(r["StockQty"]), 5)

        price_frame = tk.Frame(card, bg=bg)
        price_frame.grid(row=6, column=1, columnspan=2, sticky="w", padx=8, pady=(2, 10))
        tk.Label(price_frame, text="Цена:", font=(FONT_FAMILY, 11, "bold"), bg=bg).pack(side="left")

        price = float(r["Price"])
        disc = float(r["DiscountPercent"])
        if disc > 0:
            final_price = price * (1 - disc / 100)
            tk.Label(
                price_frame,
                text=f"{money(price)} руб.",
                font=(FONT_FAMILY, 11, "overstrike"),
                fg="red",
                bg=bg,
            ).pack(side="left", padx=(10, 6))
            tk.Label(price_frame, text=f"{money(final_price)} руб.", font=(FONT_FAMILY, 11, "bold"), bg=bg).pack(
                side="left"
            )
        else:
            tk.Label(price_frame, text=f"{money(price)} руб.", font=(FONT_FAMILY, 11, "bold"), bg=bg).pack(side="left", padx=(10, 0))

        disc_frame = tk.Frame(card, bg=bg)
        disc_frame.grid(row=0, column=3, rowspan=7, sticky="ne", padx=10, pady=10)
        tk.Label(disc_frame, text="действующая\nскидка", font=(FONT_FAMILY, 10), bg=bg, justify="center").pack()
        tk.Label(disc_frame, text=f"{int(disc)} %", font=(FONT_FAMILY, 14, "bold"), fg="red", bg=bg).pack(pady=(6, 0))

        card.grid_columnconfigure(2, weight=1)

    def _select(self, product_id: int):
        self.selected_product_id = product_id

    def _open_edit(self, product_id: int):
        if not self.can_edit:
            return
        if self._edit_window is not None and tk.Toplevel.winfo_exists(self._edit_window):
            messagebox.showinfo("Ограничение", "Нельзя открыть более одного окна редактирования.")
            self._edit_window.lift()
            return
        self._edit_window = ProductFormWindow(self, product_id=product_id)

    def _edit_selected(self):
        if not self.can_edit:
            return
        if self.selected_product_id is None:
            messagebox.showwarning("Выбор", "Выберите товар (клик по карточке), затем нажмите «Редактировать».")
            return
        self._open_edit(self.selected_product_id)

    def _add_product(self):
        if self._edit_window is not None and tk.Toplevel.winfo_exists(self._edit_window):
            messagebox.showinfo("Ограничение", "Нельзя открыть более одного окна редактирования.")
            self._edit_window.lift()
            return
        self._edit_window = ProductFormWindow(self, product_id=None)

    def _delete_selected(self):
        # Удаляет выбранный товар, если он не используется в заказах, и подчищает файл фото
        if not self.can_edit:
            return
        if self.selected_product_id is None:
            messagebox.showwarning("Выбор", "Выберите товар (клик по карточке), затем нажмите «Удалить».")
            return
        pid = self.selected_product_id

        conn = connect()
        try:
            in_order = conn.execute("SELECT 1 FROM OrderItems WHERE ProductId=? LIMIT 1", (pid,)).fetchone()
            if in_order:
                messagebox.showerror("Удаление запрещено", "Нельзя удалить товар, который присутствует в заказе.")
                return

            row = conn.execute("SELECT PhotoPath FROM Products WHERE ProductId=?", (pid,)).fetchone()
            if not row:
                return

            if not messagebox.askyesno("Подтверждение", "Удалить выбранный товар? Операция необратима."):
                return

            photo = row["PhotoPath"]
            conn.execute("DELETE FROM Products WHERE ProductId=?", (pid,))
            conn.commit()

            if photo:
                p = BASE_DIR / photo
                if p.exists() and p.is_file():
                    try:
                        p.unlink()
                    except Exception:
                        pass

            self.refresh()
        finally:
            conn.close()


class ProductFormWindow(tk.Toplevel):
    """Окно добавления или редактирования товара (доступно только администратору)."""

    def __init__(self, parent: ProductListFrame, product_id: Optional[int]):
        super().__init__(parent)
        set_window_icon(self)
        self.parent = parent
        self.product_id = product_id
        self.title("Добавление/редактирование товара")
        self.configure(bg=COLOR_BG_MAIN)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._close)

        try:
            if APP_ICON_ICO.exists():
                self.iconbitmap(str(APP_ICON_ICO))
        except Exception:
            pass

        self.vars: Dict[str, tk.Variable] = {
            "Article": tk.StringVar(),
            "ProductName": tk.StringVar(),
            "Description": tk.StringVar(),
            "Category": tk.StringVar(),
            "Manufacturer": tk.StringVar(),
            "Supplier": tk.StringVar(),
            "Unit": tk.StringVar(),
            "Price": tk.StringVar(),
            "Discount": tk.StringVar(),
            "Stock": tk.StringVar(),
        }
        self.photo_rel: Optional[str] = None
        self._photo_preview: Optional[ImageTk.PhotoImage] = None

        container = tk.Frame(self, bg=COLOR_BG_MAIN)
        container.pack(padx=14, pady=14)

        row0 = tk.Frame(container, bg=COLOR_BG_MAIN)
        row0.pack(fill="x")
        tk.Label(row0, text="ID:", font=(FONT_FAMILY, 11, "bold"), bg=COLOR_BG_MAIN).pack(side="left")
        self.id_lbl = tk.Label(row0, text="(новый)", font=(FONT_FAMILY, 11), bg=COLOR_BG_MAIN)
        self.id_lbl.pack(side="left", padx=(6, 20))

        tk.Label(row0, text="Артикул:", font=(FONT_FAMILY, 11, "bold"), bg=COLOR_BG_MAIN).pack(side="left")
        self.article_entry = tk.Entry(row0, textvariable=self.vars["Article"], font=(FONT_FAMILY, 11), width=18)
        self.article_entry.pack(side="left", padx=(6, 0))

        grid = tk.Frame(container, bg=COLOR_BG_MAIN)
        grid.pack(fill="x", pady=(10, 0))

        def lab(r, c, text):
            tk.Label(grid, text=text, font=(FONT_FAMILY, 11, "bold"), bg=COLOR_BG_MAIN).grid(row=r, column=c, sticky="w", padx=6, pady=(6, 2))

        def ent(r, c, var, width=28):
            e = tk.Entry(grid, textvariable=var, font=(FONT_FAMILY, 11), width=width)
            e.grid(row=r, column=c, sticky="w", padx=6)
            return e

        lab(0, 0, "Наименование товара")
        ent(1, 0, self.vars["ProductName"], 32)

        lab(0, 1, "Поставщик")
        self.supplier_combo = ttk.Combobox(grid, textvariable=self.vars["Supplier"], state="readonly", width=28, font=(FONT_FAMILY, 10))
        self.supplier_combo.grid(row=1, column=1, sticky="w", padx=6)

        lab(2, 0, "Категория товара")
        self.cat_combo = ttk.Combobox(grid, textvariable=self.vars["Category"], state="readonly", width=30, font=(FONT_FAMILY, 10))
        self.cat_combo.grid(row=3, column=0, sticky="w", padx=6)

        lab(2, 1, "Производитель")
        self.man_combo = ttk.Combobox(
            grid, textvariable=self.vars["Manufacturer"], state="readonly", width=26, font=(FONT_FAMILY, 10)
        )
        self.man_combo.grid(row=3, column=1, sticky="w", padx=6)

        lab(4, 0, "Единица измерения")
        self.unit_combo = ttk.Combobox(grid, textvariable=self.vars["Unit"], state="readonly", width=30, font=(FONT_FAMILY, 10))
        self.unit_combo.grid(row=5, column=0, sticky="w", padx=6)

        lab(4, 1, "Цена (руб.)")
        ent(5, 1, self.vars["Price"], 10)

        lab(6, 0, "Действующая скидка (%)")
        ent(7, 0, self.vars["Discount"], 10)

        lab(6, 1, "Кол-во на складе")
        ent(7, 1, self.vars["Stock"], 10)

        lab(8, 0, "Описание товара")
        self.desc_text = tk.Text(grid, height=4, width=60, font=(FONT_FAMILY, 11))
        self.desc_text.grid(row=9, column=0, columnspan=2, sticky="w", padx=6)

        photo_row = tk.Frame(container, bg=COLOR_BG_MAIN)
        photo_row.pack(fill="x", pady=(10, 0))
        self.photo_lbl = tk.Label(photo_row, bg=COLOR_BG_MAIN)
        self.photo_lbl.pack(side="left", padx=(0, 10))

        tk.Button(
            photo_row,
            text="Выбрать/заменить фото",
            font=(FONT_FAMILY, 11),
            bg=COLOR_BG_EXTRA,
            relief="flat",
            command=self._pick_photo,
        ).pack(side="left", ipady=2)

        btns = tk.Frame(container, bg=COLOR_BG_MAIN)
        btns.pack(fill="x", pady=(12, 0))
        tk.Button(
            btns,
            text="Сохранить",
            font=(FONT_FAMILY, 11, "bold"),
            bg=COLOR_ACCENT,
            fg="white",
            relief="flat",
            command=self._save,
            width=18,
        ).pack(side="left", ipady=3)
        tk.Button(
            btns,
            text="Назад",
            font=(FONT_FAMILY, 11),
            bg=COLOR_BG_MAIN,
            relief="groove",
            command=self._close,
            width=18,
        ).pack(side="right", ipady=3)

        self._load_lookups()
        self._load_product()

    def _load_lookups(self):
        conn = connect()
        try:
            cats = [r[0] for r in conn.execute("SELECT CategoryName FROM Categories ORDER BY CategoryName").fetchall()]
            mans = [r[0] for r in conn.execute("SELECT ManufacturerName FROM Manufacturers ORDER BY ManufacturerName").fetchall()]
            units = [r[0] for r in conn.execute("SELECT UnitName FROM Units ORDER BY UnitName").fetchall()]
            sups = [r[0] for r in conn.execute("SELECT SupplierName FROM Suppliers ORDER BY SupplierName").fetchall()]
        finally:
            conn.close()
        self.cat_combo["values"] = cats
        self.man_combo["values"] = mans
        self.unit_combo["values"] = units
        self.supplier_combo["values"] = sups

    def _load_product(self):
        if self.product_id is None:
            self.id_lbl.configure(text="(новый)")
            self._set_preview(self.photo_rel)
            return

        conn = connect()
        try:
            r = conn.execute(
                """
                SELECT p.ProductId, p.Article, p.ProductName, p.Description, p.Price, p.DiscountPercent, p.StockQty,
                       p.PhotoPath, c.CategoryName, m.ManufacturerName, s.SupplierName, u.UnitName
                FROM Products p
                JOIN Categories c ON c.CategoryId = p.CategoryId
                JOIN Manufacturers m ON m.ManufacturerId = p.ManufacturerId
                JOIN Suppliers s ON s.SupplierId = p.SupplierId
                JOIN Units u ON u.UnitId = p.UnitId
                WHERE p.ProductId = ?
                """,
                (self.product_id,),
            ).fetchone()
        finally:
            conn.close()

        if not r:
            messagebox.showerror("Ошибка", "Товар не найден.")
            self._close()
            return

        self.id_lbl.configure(text=str(r["ProductId"]))
        self.vars["Article"].set(r["Article"])
        self.vars["ProductName"].set(r["ProductName"])
        self.vars["Supplier"].set(r["SupplierName"])
        self.vars["Category"].set(r["CategoryName"])
        self.vars["Manufacturer"].set(r["ManufacturerName"])
        self.vars["Unit"].set(r["UnitName"])
        self.vars["Price"].set(str(r["Price"]))
        self.vars["Discount"].set(str(r["DiscountPercent"]))
        self.vars["Stock"].set(str(r["StockQty"]))

        self.desc_text.delete("1.0", "end")
        self.desc_text.insert("1.0", r["Description"] or "")

        self.photo_rel = r["PhotoPath"]
        self._set_preview(self.photo_rel)

    def _set_preview(self, rel_path: Optional[str]):
        path = None
        if rel_path:
            p = BASE_DIR / rel_path
            if p.exists():
                path = p
        if path is None:
            path = PLACEHOLDER

        img = Image.open(path).convert("RGBA")
        img.thumbnail((150, 100), Image.Resampling.LANCZOS)
        self._photo_preview = ImageTk.PhotoImage(img)
        self.photo_lbl.configure(image=self._photo_preview)

    def _pick_photo(self):
        # Выбор изображения, масштабирование до 300x200, сохранение в assets/images
        path = filedialog.askopenfilename(
            title="Выбор изображения",
            filetypes=[("Изображения", "*.png;*.jpg;*.jpeg"), ("Все файлы", "*.*")],
        )
        if not path:
            return

        try:
            img = Image.open(path).convert("RGBA")
        except Exception:
            messagebox.showerror("Ошибка", "Не удалось открыть изображение.")
            return

        img.thumbnail((300, 200), Image.Resampling.LANCZOS)

        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        fname = f"user_{self.product_id or 'new'}_{os.getpid()}_{Path(path).stem}.png"
        dst = IMAGES_DIR / fname
        img.save(dst)

        if self.photo_rel:
            old = BASE_DIR / self.photo_rel
            if old.exists() and old.is_file() and old.name != PLACEHOLDER.name:
                try:
                    old.unlink()
                except Exception:
                    pass

        self.photo_rel = str(Path("assets/images") / fname)
        self._set_preview(self.photo_rel)

    def _validate(self) -> Optional[str]:
        # Проверяем обязательные поля и допустимость числовых значений
        if not self.vars["Article"].get().strip():
            return "Артикул обязателен."
        if not self.vars["ProductName"].get().strip():
            return "Наименование товара обязательно."
        if not self.vars["Supplier"].get().strip():
            return "Поставщик обязателен."
        if not self.vars["Category"].get().strip():
            return "Выберите категорию товара."
        if not self.vars["Manufacturer"].get().strip():
            return "Выберите производителя."
        if not self.vars["Unit"].get().strip():
            return "Выберите единицу измерения."

        try:
            price = float(self.vars["Price"].get().strip())
            if price < 0:
                return "Цена не может быть отрицательной."
        except ValueError:
            return "Цена должна быть числом."

        try:
            disc = float(self.vars["Discount"].get().strip() or "0")
            if disc < 0:
                return "Скидка не может быть отрицательной."
        except ValueError:
            return "Скидка должна быть числом."

        try:
            stock = int(float(self.vars["Stock"].get().strip()))
            if stock < 0:
                return "Количество на складе не может быть отрицательным."
        except ValueError:
            return "Количество на складе должно быть целым числом."

        return None

    def _save(self):
        # Валидируем, находим ID справочников и выполняем INSERT или UPDATE
        err = self._validate()
        if err:
            messagebox.showerror("Ошибка ввода", err)
            return

        article = self.vars["Article"].get().strip()
        name = self.vars["ProductName"].get().strip()
        supplier = self.vars["Supplier"].get().strip()
        category = self.vars["Category"].get().strip()
        manufacturer = self.vars["Manufacturer"].get().strip()
        unit = self.vars["Unit"].get().strip()
        price = float(self.vars["Price"].get().strip())
        discount = float(self.vars["Discount"].get().strip() or "0")
        stock = int(float(self.vars["Stock"].get().strip()))
        desc = self.desc_text.get("1.0", "end").strip()

        conn = connect()
        try:
            sup_id = conn.execute("SELECT SupplierId FROM Suppliers WHERE SupplierName=?", (supplier,)).fetchone()
            if sup_id is None:
                messagebox.showerror("Ошибка", "Поставщик не найден.")
                return
            sup_id = sup_id[0]

            cat_id = conn.execute("SELECT CategoryId FROM Categories WHERE CategoryName=?", (category,)).fetchone()[0]
            man_id = conn.execute("SELECT ManufacturerId FROM Manufacturers WHERE ManufacturerName=?", (manufacturer,)).fetchone()[0]
            unit_id = conn.execute("SELECT UnitId FROM Units WHERE UnitName=?", (unit,)).fetchone()[0]

            if self.product_id is None:
                try:
                    conn.execute(
                        """
                        INSERT INTO Products(
                            Article, ProductName, Description, CategoryId, ManufacturerId, SupplierId,
                            UnitId, Price, DiscountPercent, StockQty, PhotoPath
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (article, name, desc, cat_id, man_id, sup_id, unit_id, price, discount, stock, self.photo_rel),
                    )
                except sqlite3.IntegrityError:
                    messagebox.showerror("Ошибка", "Артикул должен быть уникальным. Проверьте значение.")
                    return
            else:
                other = conn.execute(
                    "SELECT 1 FROM Products WHERE Article=? AND ProductId<>?", (article, self.product_id)
                ).fetchone()
                if other:
                    messagebox.showerror("Ошибка", "Артикул должен быть уникальным. Проверьте значение.")
                    return

                conn.execute(
                    """
                    UPDATE Products
                    SET Article=?, ProductName=?, Description=?, CategoryId=?, ManufacturerId=?, SupplierId=?,
                        UnitId=?, Price=?, DiscountPercent=?, StockQty=?, PhotoPath=?
                    WHERE ProductId=?
                    """,
                    (article, name, desc, cat_id, man_id, sup_id, unit_id, price, discount, stock, self.photo_rel, self.product_id),
                )

            conn.commit()
        finally:
            conn.close()

        self.parent.refresh()
        self._close()

    def _close(self):
        self.parent._edit_window = None
        self.destroy()


class OrdersFrame(tk.Frame):
    """Экран просмотра заказов в виде таблицы с возможностью управления (для администратора)."""

    def __init__(self, master: App):
        super().__init__(master, bg=COLOR_BG_MAIN)
        self.master = master
        self.role = master.session.role
        self.can_edit = self.role == "Администратор"

        header = tk.Frame(self, bg=COLOR_BG_EXTRA)
        header.pack(fill="x")
        tk.Label(header, text="Заказы", font=(FONT_FAMILY, 14, "bold"), bg=COLOR_BG_EXTRA).pack(
            side="left", padx=12, pady=10
        )

        right = tk.Frame(header, bg=COLOR_BG_EXTRA)
        right.pack(side="right", padx=12)
        tk.Label(right, text=self.master.session.full_name, font=(FONT_FAMILY, 12, "bold"), bg=COLOR_BG_EXTRA).pack(
            side="left", padx=(0, 10)
        )
        tk.Button(
            right,
            text="Выйти",
            font=(FONT_FAMILY, 11, "bold"),
            bg="#FF6B6B",
            fg="white",
            relief="flat",
            command=self.master.show_login,
        ).pack(side="left", pady=6)

        actions = tk.Frame(self, bg=COLOR_BG_MAIN)
        actions.pack(fill="x", padx=12, pady=10)

        tk.Button(
            actions,
            text="Назад",
            font=(FONT_FAMILY, 11),
            bg=COLOR_BG_MAIN,
            relief="groove",
            command=self.master.show_products,
        ).pack(side="left", ipady=2)

        if self.can_edit:
            tk.Button(
                actions,
                text="+ Добавить",
                font=(FONT_FAMILY, 11),
                bg=COLOR_ACCENT,
                fg="white",
                relief="flat",
                command=self._add,
            ).pack(side="left", padx=(10, 0), ipady=2)

            tk.Button(
                actions,
                text="Редактировать",
                font=(FONT_FAMILY, 11),
                bg=COLOR_BG_EXTRA,
                relief="flat",
                command=self._edit,
            ).pack(side="left", padx=10, ipady=2)

            tk.Button(
                actions,
                text="Удалить",
                font=(FONT_FAMILY, 11),
                bg="#FF6B6B",
                fg="white",
                relief="flat",
                command=self._delete,
            ).pack(side="left", ipady=2)

        cols = ("num", "order_date", "delivery", "pickup", "customer", "code", "status")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=14)
        headings = [
            ("num", "Номер"),
            ("order_date", "Дата заказа"),
            ("delivery", "Дата доставки"),
            ("pickup", "Пункт выдачи"),
            ("customer", "Клиент"),
            ("code", "Код"),
            ("status", "Статус"),
        ]
        for c, t in headings:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=110 if c != "pickup" else 220, anchor="w")

        self.tree.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.selected_order_id: Optional[int] = None
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        self.refresh()

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        self.selected_order_id = int(sel[0]) if sel else None

    def refresh(self):
        for i in self.tree.get_children():
            self.tree.delete(i)

        conn = connect()
        try:
            rows = conn.execute(
                """
                SELECT o.OrderId, o.OrderNumber, o.OrderDate, o.DeliveryDate,
                       pp.Address, u.FullName, o.ReceiveCode, st.StatusName
                FROM Orders o
                JOIN PickupPoints pp ON pp.PickupPointId = o.PickupPointId
                LEFT JOIN Users u ON u.UserId = o.CustomerUserId
                JOIN OrderStatuses st ON st.StatusId = o.StatusId
                ORDER BY o.OrderNumber
                """
            ).fetchall()
        finally:
            conn.close()

        for r in rows:
            self.tree.insert(
                "",
                "end",
                iid=str(r["OrderId"]),
                values=(
                    r["OrderNumber"],
                    r["OrderDate"],
                    r["DeliveryDate"],
                    r["Address"],
                    r["FullName"] or "",
                    r["ReceiveCode"],
                    r["StatusName"],
                ),
            )

    def _add(self):
        OrderFormWindow(self, None)

    def _edit(self):
        if self.selected_order_id is None:
            messagebox.showwarning("Выбор", "Выберите заказ в таблице.")
            return
        OrderFormWindow(self, self.selected_order_id)

    def _delete(self):
        if self.selected_order_id is None:
            messagebox.showwarning("Выбор", "Выберите заказ в таблице.")
            return
        if not messagebox.askyesno("Подтверждение", "Удалить выбранный заказ? Операция необратима."):
            return
        conn = connect()
        try:
            conn.execute("DELETE FROM Orders WHERE OrderId=?", (self.selected_order_id,))
            conn.commit()
        finally:
            conn.close()
        self.refresh()


class OrderFormWindow(tk.Toplevel):
    """Окно добавления или редактирования заказа (доступно администратору)."""

    def __init__(self, parent: OrdersFrame, order_id: Optional[int]):
        super().__init__(parent)
        set_window_icon(self)
        self.parent = parent
        self.order_id = order_id
        self.title("Добавление/редактирование заказа")
        self.configure(bg=COLOR_BG_MAIN)
        self.resizable(False, False)

        self.vars: Dict[str, tk.Variable] = {
            "OrderNumber": tk.StringVar(),
            "OrderDate": tk.StringVar(),
            "DeliveryDate": tk.StringVar(),
            "PickupPoint": tk.StringVar(),
            "Customer": tk.StringVar(),
            "ReceiveCode": tk.StringVar(),
            "Status": tk.StringVar(),
        }

        wrap = tk.Frame(self, bg=COLOR_BG_MAIN)
        wrap.pack(padx=14, pady=14)

        def row(r, label, widget):
            tk.Label(wrap, text=label, font=(FONT_FAMILY, 11, "bold"), bg=COLOR_BG_MAIN).grid(row=r, column=0, sticky="w", padx=6, pady=(6, 2))
            widget.grid(row=r, column=1, sticky="w", padx=6)

        row(0, "Номер заказа", tk.Entry(wrap, textvariable=self.vars["OrderNumber"], font=(FONT_FAMILY, 11), width=18))
        row(1, "Дата заказа (YYYY-MM-DD)", tk.Entry(wrap, textvariable=self.vars["OrderDate"], font=(FONT_FAMILY, 11), width=18))
        row(2, "Дата доставки (YYYY-MM-DD)", tk.Entry(wrap, textvariable=self.vars["DeliveryDate"], font=(FONT_FAMILY, 11), width=18))

        self.pp_combo = ttk.Combobox(wrap, textvariable=self.vars["PickupPoint"], state="readonly", width=48, font=(FONT_FAMILY, 10))
        row(3, "Адрес пункта выдачи", self.pp_combo)

        self.cust_combo = ttk.Combobox(wrap, textvariable=self.vars["Customer"], state="readonly", width=48, font=(FONT_FAMILY, 10))
        row(4, "Клиент", self.cust_combo)

        row(5, "Код для получения", tk.Entry(wrap, textvariable=self.vars["ReceiveCode"], font=(FONT_FAMILY, 11), width=18))

        self.status_combo = ttk.Combobox(wrap, textvariable=self.vars["Status"], state="readonly", width=24, font=(FONT_FAMILY, 10))
        row(6, "Статус", self.status_combo)

        btns = tk.Frame(wrap, bg=COLOR_BG_MAIN)
        btns.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        tk.Button(
            btns,
            text="Сохранить",
            font=(FONT_FAMILY, 11, "bold"),
            bg=COLOR_ACCENT,
            fg="white",
            relief="flat",
            command=self._save,
            width=18,
        ).pack(side="left", ipady=3)
        tk.Button(
            btns,
            text="Назад",
            font=(FONT_FAMILY, 11),
            bg=COLOR_BG_MAIN,
            relief="groove",
            command=self.destroy,
            width=18,
        ).pack(side="right", ipady=3)

        self._load_lookups()
        self._load_order()

    def _load_lookups(self):
        conn = connect()
        try:
            pps = conn.execute("SELECT PickupPointId, Address FROM PickupPoints ORDER BY PickupPointId").fetchall()
            sts = [r[0] for r in conn.execute("SELECT StatusName FROM OrderStatuses ORDER BY StatusName").fetchall()]
            customers = [r[0] for r in conn.execute("SELECT FullName FROM Users ORDER BY FullName").fetchall()]
        finally:
            conn.close()

        self.pp_map = {a: int(i) for i, a in pps}
        self.pp_combo["values"] = list(self.pp_map.keys())
        self.status_combo["values"] = sts
        self.cust_combo["values"] = ["", *customers]

    def _load_order(self):
        if self.order_id is None:
            return
        conn = connect()
        try:
            r = conn.execute(
                """
                SELECT o.OrderNumber, o.OrderDate, o.DeliveryDate, pp.Address,
                       u.FullName, o.ReceiveCode, st.StatusName
                FROM Orders o
                JOIN PickupPoints pp ON pp.PickupPointId = o.PickupPointId
                LEFT JOIN Users u ON u.UserId = o.CustomerUserId
                JOIN OrderStatuses st ON st.StatusId = o.StatusId
                WHERE o.OrderId=?
                """,
                (self.order_id,),
            ).fetchone()
        finally:
            conn.close()
        if not r:
            return
        self.vars["OrderNumber"].set(str(r["OrderNumber"]))
        self.vars["OrderDate"].set(r["OrderDate"])
        self.vars["DeliveryDate"].set(r["DeliveryDate"])
        self.vars["PickupPoint"].set(r["Address"])
        self.vars["Customer"].set(r["FullName"] or "")
        self.vars["ReceiveCode"].set(str(r["ReceiveCode"]))
        self.vars["Status"].set(r["StatusName"])

    def _save(self):
        try:
            num = int(self.vars["OrderNumber"].get().strip())
        except ValueError:
            messagebox.showerror("Ошибка ввода", "Номер заказа должен быть целым числом.")
            return

        od = self.vars["OrderDate"].get().strip()
        dd = self.vars["DeliveryDate"].get().strip()
        if not od or not dd:
            messagebox.showerror("Ошибка ввода", "Заполните даты заказа и доставки.")
            return

        pp_addr = self.vars["PickupPoint"].get().strip()
        if not pp_addr:
            messagebox.showerror("Ошибка ввода", "Выберите пункт выдачи.")
            return
        pp_id = self.pp_map.get(pp_addr)

        cust_name = self.vars["Customer"].get().strip()
        status = self.vars["Status"].get().strip()
        if not status:
            messagebox.showerror("Ошибка ввода", "Выберите статус заказа.")
            return

        try:
            code = int(self.vars["ReceiveCode"].get().strip())
        except ValueError:
            messagebox.showerror("Ошибка ввода", "Код для получения должен быть числом.")
            return

        conn = connect()
        try:
            status_id = conn.execute("SELECT StatusId FROM OrderStatuses WHERE StatusName=?", (status,)).fetchone()[0]
            cust_id = None
            if cust_name:
                row = conn.execute("SELECT UserId FROM Users WHERE FullName=?", (cust_name,)).fetchone()
                cust_id = row[0] if row else None

            if self.order_id is None:
                try:
                    conn.execute(
                        """
                        INSERT INTO Orders(OrderNumber, OrderDate, DeliveryDate, PickupPointId, CustomerUserId, ReceiveCode, StatusId)
                        VALUES (?,?,?,?,?,?,?)
                        """,
                        (num, od, dd, pp_id, cust_id, code, status_id),
                    )
                except sqlite3.IntegrityError:
                    messagebox.showerror("Ошибка", "Номер заказа должен быть уникальным.")
                    return
            else:
                other = conn.execute(
                    "SELECT 1 FROM Orders WHERE OrderNumber=? AND OrderId<>?", (num, self.order_id)
                ).fetchone()
                if other:
                    messagebox.showerror("Ошибка", "Номер заказа должен быть уникальным.")
                    return

                conn.execute(
                    """
                    UPDATE Orders
                    SET OrderNumber=?, OrderDate=?, DeliveryDate=?, PickupPointId=?, CustomerUserId=?, ReceiveCode=?, StatusId=?
                    WHERE OrderId=?
                    """,
                    (num, od, dd, pp_id, cust_id, code, status_id, self.order_id),
                )

            conn.commit()
        finally:
            conn.close()

        self.parent.refresh()
        self.destroy()


if __name__ == "__main__":
    root = App()
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    root.mainloop()
