import hmac
import os

import flet as ft

def main(page: ft.Page):
    page.title = "Neon OS - Móvil"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0f172a"
    page.window_width = 400
    page.window_height = 800

    # ==========================================
    # VISTAS (MENÚS ESPECIALES)
    # ==========================================
    def view_admin():
        return ft.View(
            "/admin",
            [
                ft.AppBar(title=ft.Text("Panel de Administrador"), bgcolor="#ef4444"),
                ft.Text("Bienvenido, Administrador Supremo", size=20, weight="bold", color="#ef4444"),
                ft.ElevatedButton("Monitoreo de Sistema", icon=ft.icons.MONITOR),
                ft.ElevatedButton("Cerrar Sesión", on_click=lambda _: page.go("/"))
            ],
            bgcolor="#0f172a",
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            vertical_alignment=ft.MainAxisAlignment.CENTER,
            spacing=20
        )

    def view_profesor():
        return ft.View(
            "/profesor",
            [
                ft.AppBar(title=ft.Text("Misiones (Profesor)"), bgcolor="#10b981"),
                ft.Text("Bienvenido, Profesor", size=20, weight="bold", color="#10b981"),
                ft.ElevatedButton("Gestionar Materia", icon=ft.icons.BOOK),
                ft.ElevatedButton("Cerrar Sesión", on_click=lambda _: page.go("/"))
            ],
            bgcolor="#0f172a",
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            vertical_alignment=ft.MainAxisAlignment.CENTER,
            spacing=20
        )

    def view_estudiante():
        return ft.View(
            "/estudiante",
            [
                ft.AppBar(title=ft.Text("Arena (Estudiante)"), bgcolor="#38bdf8"),
                ft.Text("Bienvenido, Estudiante", size=20, weight="bold", color="#38bdf8"),
                ft.ElevatedButton("Ver Encuestas", icon=ft.icons.POLL),
                ft.ElevatedButton("Cerrar Sesión", on_click=lambda _: page.go("/"))
            ],
            bgcolor="#0f172a",
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            vertical_alignment=ft.MainAxisAlignment.CENTER,
            spacing=20
        )

    # ==========================================
    # VISTA DE LOGIN
    # ==========================================
    # La clave del administrador NO está en el código: sale de la variable de entorno NEON_ADMIN_CLAVE (ver docs/CORREO.md).
    clave_admin = os.environ.get("NEON_ADMIN_CLAVE", "")
    usuario_admin = os.environ.get("NEON_ADMIN_USUARIO", "").strip().lower() or "luix"
    # Cuentas de demostración de este prototipo: solo existen si defines NEON_DEMO_CLAVE (no hay clave escrita en el código).
    clave_demo = os.environ.get("NEON_DEMO_CLAVE", "").strip()
    demo_ok = lambda u_, p_, usuario_: bool(clave_demo) and u_ == usuario_ and hmac.compare_digest(p_.encode(), clave_demo.encode())

    def procesar_login(e):
        u = txt_usuario.value.lower().strip()
        p = txt_password.value.strip()
        r = dropdown_rol.value
        
        if not u or not p or not r:
            mostrar_error("Por favor llena todos los campos.")
            return

        # SIMULACIÓN DE CONEXIÓN A BASE DE DATOS COMPARTIDA
        # (Temporalmente simulado hasta unificar la DB local SQLite con los roles)
        if r == "Administrador" and clave_admin.strip() and u == usuario_admin and hmac.compare_digest(p.encode(), clave_admin.encode()):
            page.go("/admin")
        elif r == "Profesor" and demo_ok(u, p, "camilo"):
            page.go("/profesor")
        elif r == "Estudiante" and demo_ok(u, p, "daniel"):
            page.go("/estudiante")
        else:
            mostrar_error("Credenciales incorrectas o Rol equivocado.")

    def mostrar_error(mensaje):
        page.snack_bar = ft.SnackBar(ft.Text(mensaje), bgcolor="#ef4444")
        page.snack_bar.open = True
        page.update()

    titulo = ft.Text("Acceso NeonOS", size=30, weight=ft.FontWeight.BOLD, color="#f8fafc")
    txt_usuario = ft.TextField(label="Usuario", width=300, border_radius=10, border_color="#38bdf8")
    txt_password = ft.TextField(label="Contraseña", password=True, can_reveal_password=True, width=300, border_radius=10, border_color="#38bdf8")
    dropdown_rol = ft.Dropdown(
        width=300,
        label="Selecciona tu Rol",
        border_color="#38bdf8",
        options=[
            ft.dropdown.Option("Estudiante"),
            ft.dropdown.Option("Profesor"),
            ft.dropdown.Option("Administrador"),
        ]
    )

    btn_login = ft.Button(
        content=ft.Text("Iniciar Sesión", weight="bold"), 
        width=300, height=50,
        style=ft.ButtonStyle(color="#f8fafc", bgcolor="#818cf8", shape=ft.RoundedRectangleBorder(radius=10)),
        on_click=procesar_login
    )

    view_login = ft.View(
        "/",
        [
            ft.Container(
                content=ft.Column(
                    [titulo, dropdown_rol, txt_usuario, txt_password, btn_login],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=20
                ),
                bgcolor="#334155", padding=40, border_radius=20,
            )
        ],
        bgcolor="#0f172a",
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        vertical_alignment=ft.MainAxisAlignment.CENTER,
    )

    # ==========================================
    # MANEJO DE RUTAS (NAVEGACIÓN MÓVIL)
    # ==========================================
    def route_change(route):
        page.views.clear()
        if page.route == "/":
            page.views.append(view_login)
        elif page.route == "/admin":
            page.views.append(view_admin())
        elif page.route == "/profesor":
            page.views.append(view_profesor())
        elif page.route == "/estudiante":
            page.views.append(view_estudiante())
        page.update()

    def view_pop(view):
        page.views.pop()
        top_view = page.views[-1]
        page.go(top_view.route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop
    page.go(page.route)

if __name__ == "__main__":
    import entorno                      # lee el .env junto a la app (lo definido en el sistema tiene prioridad)
    entorno.cargar_env()
    ft.run(main)
