from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib.pyplot as plt
import pandas as pd

from .config import (
    DEFAULT_OUTPUT_XLSX,
    DEFAULT_OUTPUT_DGA_XLSX,
    DEFAULT_OUTPUT_RESUMEN_DIARIO_XLSX,
    DGA_HORA_DEFAULT,
    REGLA_DIA_OPERATIVO,
    TZ_CHILE,
    VARIABLE_AGUA,
)
from .database import obtener_variables
from .dga_report import guardar_reporte_dga_excel
from .processing import (
    calcular_kpis,
    calcular_turnos_por_intervalos,
    preparar_dataframe,
)
from .reports import (
    calcular_resumen_agua,
    calcular_tendencia_agua,
    calcular_resumen_diario_variable,
    guardar_mapa_agua_excel,
    guardar_resumen_diario_variable_excel,
)


class TelemetryApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.combo_variable: ttk.Combobox
        self.entry_inicio: ttk.Entry
        self.entry_fin: ttk.Entry
        self.combo_hora_inicio: ttk.Combobox
        self.combo_hora_fin: ttk.Combobox

        self._configurar_ventana()
        self._crear_interfaz()
        self._cargar_variables()

    def _configurar_ventana(self) -> None:
        self.root.title("Visualizador de Telemetría - Diagnóstico")
        self.root.geometry("1120x470")
        self.root.minsize(900, 430)

    def _crear_interfaz(self) -> None:
        frame = ttk.Frame(self.root, padding=15)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="Selecciona variable / equipo:",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        self.combo_variable = ttk.Combobox(
            frame,
            state="readonly",
            width=48,
        )
        self.combo_variable.grid(
            row=0,
            column=1,
            columnspan=4,
            sticky="w",
            pady=(0, 8),
        )

        fecha_frame = ttk.LabelFrame(
            frame,
            text="Filtro de fecha y hora",
            padding=10,
        )
        fecha_frame.grid(
            row=1,
            column=0,
            columnspan=5,
            sticky="ew",
            pady=(0, 15),
        )

        horas_disponibles = [
            f"{hora:02d}:{minuto:02d}"
            for hora in range(24)
            for minuto in range(0, 60, 5)
        ]
        ahora = datetime.now(TZ_CHILE)
        minuto_redondeado = (ahora.minute // 5) * 5
        hora_fin_default = f"{ahora.hour:02d}:{minuto_redondeado:02d}"

        ttk.Label(fecha_frame, text="Desde fecha:").grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 5),
        )

        self.entry_inicio = ttk.Entry(fecha_frame, width=13)
        self.entry_inicio.grid(
            row=0,
            column=1,
            sticky="w",
            padx=(0, 8),
        )
        self.entry_inicio.insert(0, ahora.strftime("%Y-%m-01"))

        ttk.Label(fecha_frame, text="Hora:").grid(
            row=0,
            column=2,
            sticky="w",
            padx=(0, 5),
        )

        self.combo_hora_inicio = ttk.Combobox(
            fecha_frame,
            state="readonly",
            width=7,
            values=horas_disponibles,
        )
        self.combo_hora_inicio.grid(
            row=0,
            column=3,
            sticky="w",
            padx=(0, 25),
        )
        self.combo_hora_inicio.set("00:00")

        ttk.Label(fecha_frame, text="Hasta fecha:").grid(
            row=0,
            column=4,
            sticky="w",
            padx=(0, 5),
        )

        self.entry_fin = ttk.Entry(fecha_frame, width=13)
        self.entry_fin.grid(
            row=0,
            column=5,
            sticky="w",
            padx=(0, 8),
        )
        self.entry_fin.insert(0, ahora.strftime("%Y-%m-%d"))

        ttk.Label(fecha_frame, text="Hora:").grid(
            row=0,
            column=6,
            sticky="w",
            padx=(0, 5),
        )

        self.combo_hora_fin = ttk.Combobox(
            fecha_frame,
            state="readonly",
            width=7,
            values=horas_disponibles,
        )
        self.combo_hora_fin.grid(row=0, column=7, sticky="w")
        self.combo_hora_fin.set(hora_fin_default)

        ttk.Label(
            fecha_frame,
            text="Formato: AAAA-MM-DD | horas en intervalos de 5 minutos",
            foreground="gray",
        ).grid(
            row=1,
            column=0,
            columnspan=8,
            sticky="w",
            pady=(8, 0),
        )

        botones = ttk.LabelFrame(frame, text="Acciones", padding=10)
        botones.grid(row=2, column=0, columnspan=5, sticky="ew")

        definiciones = [
            ("Graficar acumulado", self.graficar_acumulado),
            ("Graficar diferencia", self.graficar_diferencia),
            ("Ver últimos 200", self.mostrar_ultimos_200),
            ("Resumen turnos", self.mostrar_resumen_turnos),
            ("Probar agua local", self.probar_resumen_agua_local),
            ("Probar tendencia agua", self.probar_tendencia_agua_local),
            ("Generar MapaAgua.xlsx", self.generar_mapa_agua_default),
            ("Guardar Excel como...", self.generar_mapa_agua_como),
            ("Generar reporte DGA", self.abrir_generador_dga),
            ("Ver resumen diario", self.mostrar_resumen_diario),
            ("Guardar resumen diario", self.generar_resumen_diario_como),
        ]

        for indice, (texto, comando) in enumerate(definiciones):
            fila = indice // 3
            columna = indice % 3
            ttk.Button(
                botones,
                text=texto,
                command=comando,
                width=28,
            ).grid(
                row=fila,
                column=columna,
                padx=5,
                pady=5,
                sticky="ew",
            )

        for columna in range(3):
            botones.columnconfigure(columna, weight=1)

        ttk.Label(
            frame,
            text=(
                "Modo diagnóstico: rango seleccionable por fecha y hora, datos crudos, "
                "turnos por diferencias, resumen diario y generación de MapaAgua.xlsx."
            ),
            foreground="gray",
        ).grid(
            row=3,
            column=0,
            columnspan=5,
            sticky="w",
            pady=(15, 0),
        )

        ttk.Label(
            frame,
            text=(
                f"Archivo por defecto: {DEFAULT_OUTPUT_XLSX}"
            ),
            foreground="gray",
        ).grid(
            row=4,
            column=0,
            columnspan=5,
            sticky="w",
            pady=(5, 0),
        )

        frame.columnconfigure(1, weight=1)

    def _cargar_variables(self) -> None:
        try:
            variables = obtener_variables()
            self.combo_variable["values"] = variables

            if VARIABLE_AGUA in variables:
                self.combo_variable.set(VARIABLE_AGUA)
            elif variables:
                self.combo_variable.current(0)

        except Exception as exc:
            messagebox.showerror(
                "Error de carga",
                f"No fue posible conectar a la BD.\n\n{exc}",
            )

    def _obtener_variable(self) -> str | None:
        nombre = self.combo_variable.get().strip()

        if not nombre:
            messagebox.showwarning(
                "Atención",
                "Selecciona una variable.",
            )
            return None

        return nombre

    def _obtener_dataframe(self, nombre: str) -> pd.DataFrame:
        fecha_inicio = self.entry_inicio.get().strip()
        hora_inicio = self.combo_hora_inicio.get().strip()
        fecha_fin = self.entry_fin.get().strip()
        hora_fin = self.combo_hora_fin.get().strip()

        try:
            return preparar_dataframe(
                nombre,
                fecha_inicio,
                fecha_fin,
                hora_inicio,
                hora_fin,
            )
        except ValueError as exc:
            messagebox.showerror(
                "Rango inválido",
                str(exc),
            )
            return pd.DataFrame()

    def _mostrar_texto(
        self,
        titulo: str,
        contenido: str,
        geometry: str,
    ) -> None:
        ventana = tk.Toplevel(self.root)
        ventana.title(titulo)
        ventana.geometry(geometry)

        frame = ttk.Frame(ventana)
        frame.pack(fill="both", expand=True)

        texto = tk.Text(frame, wrap="none")
        scroll_y = ttk.Scrollbar(
            frame,
            orient="vertical",
            command=texto.yview,
        )
        scroll_x = ttk.Scrollbar(
            frame,
            orient="horizontal",
            command=texto.xview,
        )

        texto.configure(
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set,
        )

        texto.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        texto.insert("end", contenido)
        texto.config(state="disabled")

    def graficar_acumulado(self) -> None:
        nombre = self._obtener_variable()
        if nombre is None:
            return

        try:
            df = self._obtener_dataframe(nombre)

            if df.empty:
                messagebox.showinfo(
                    "Sin datos",
                    f"No hay datos para '{nombre}' en ese rango.",
                )
                return

            plt.figure(figsize=(11, 5))
            plt.plot(
                df["fecha_hora_chile"],
                df["valor"],
                label="Acumulado real",
            )
            plt.title(f"Tendencia acumulada real - {nombre}")
            plt.xlabel("Fecha / hora Chile")
            plt.ylabel("Valor acumulado")
            plt.grid(True)
            plt.tight_layout()
            plt.show()

        except Exception as exc:
            messagebox.showerror(
                "Error",
                f"No fue posible graficar.\n\n{exc}",
            )

    def graficar_diferencia(self) -> None:
        nombre = self._obtener_variable()
        if nombre is None:
            return

        try:
            df = self._obtener_dataframe(nombre)

            if df.empty:
                messagebox.showinfo(
                    "Sin datos",
                    f"No hay datos para '{nombre}' en ese rango.",
                )
                return

            plt.figure(figsize=(11, 5))
            plt.plot(
                df["fecha_hora_chile"],
                df["consumo_tramo"],
                label="Diferencia entre registros",
            )
            plt.title(f"Diferencia entre registros - {nombre}")
            plt.xlabel("Fecha / hora Chile")
            plt.ylabel("Consumo / diferencia")
            plt.grid(True)
            plt.tight_layout()
            plt.show()

        except Exception as exc:
            messagebox.showerror(
                "Error",
                f"No fue posible graficar.\n\n{exc}",
            )

    def mostrar_ultimos_200(self) -> None:
        nombre = self._obtener_variable()
        if nombre is None:
            return

        try:
            df = self._obtener_dataframe(nombre)

            if df.empty:
                messagebox.showinfo(
                    "Sin datos",
                    f"No hay datos para '{nombre}' en ese rango.",
                )
                return

            columnas = [
                "fecha",
                "hora",
                "turno",
                "valor",
                "consumo_tramo",
            ]
            df_ultimos = df.tail(200)[columnas].copy()

            self._mostrar_texto(
                f"Últimos 200 registros - {nombre}",
                df_ultimos.to_string(index=False),
                "850x420",
            )

        except Exception as exc:
            messagebox.showerror(
                "Error",
                f"No fue posible mostrar registros.\n\n{exc}",
            )

    def mostrar_resumen_turnos(self) -> None:
        nombre = self._obtener_variable()
        if nombre is None:
            return

        try:
            df = self._obtener_dataframe(nombre)

            if df.empty:
                messagebox.showinfo(
                    "Sin datos",
                    f"No hay datos para '{nombre}' en ese rango.",
                )
                return

            kpis = calcular_kpis(df)
            resumen_turnos = calcular_turnos_por_intervalos(df)

            total_periodo = kpis["consumo_total_periodo"]
            total_turnos = resumen_turnos["consumo_total"].sum()
            diferencia = total_periodo - total_turnos

            valor_inicial = kpis["valor_inicial"]
            valor_final = kpis["valor_final"]

            valor_inicial_txt = (
                "Sin dato"
                if valor_inicial is None
                else f"{valor_inicial:,.2f}"
            )
            valor_final_txt = (
                "Sin dato"
                if valor_final is None
                else f"{valor_final:,.2f}"
            )

            salida = [
                "RESUMEN DE CONSUMO POR TURNOS",
                "=" * 70,
                f"Variable / equipo       : {nombre}",
                (
                    "Desde                  : "
                    f"{self.entry_inicio.get().strip()} "
                    f"{self.combo_hora_inicio.get().strip()}"
                ),
                (
                    "Hasta                  : "
                    f"{self.entry_fin.get().strip()} "
                    f"{self.combo_hora_fin.get().strip()}"
                ),
                f"Registros procesados    : {kpis['registros']}",
                "",
                "CONSUMO TOTAL POR RESTA DE ACUMULADOS",
                "-" * 70,
                f"Valor inicial           : {valor_inicial_txt}",
                f"Valor final             : {valor_final_txt}",
                f"Consumo total período   : {total_periodo:,.2f}",
                "",
                "DISTRIBUCIÓN POR TURNOS",
                "-" * 70,
                resumen_turnos.to_string(index=False),
                "",
                "VALIDACIÓN",
                "-" * 70,
                f"Suma turnos             : {total_turnos:,.2f}",
                f"Diferencia total-turnos : {diferencia:,.2f}",
                "",
            ]

            if abs(diferencia) < 0.01:
                salida.append(
                    "Estado                  : OK, los turnos cuadran con el total."
                )
            else:
                salida.extend([
                    "Estado                  : Revisar. Hay diferencia entre total y turnos.",
                    "",
                    "Posibles causas:",
                    "- Primer registro del período tiene consumo_tramo = 0.",
                    "- Hubo reinicio del acumulado.",
                    "- Hay saltos negativos recortados a cero.",
                    "- El rango seleccionado corta un intervalo entre registros.",
                ])

            self._mostrar_texto(
                f"Resumen por turnos - {nombre}",
                "\n".join(salida),
                "720x430",
            )

        except Exception as exc:
            messagebox.showerror(
                "Error",
                f"No fue posible calcular turnos.\n\n{exc}",
            )

    def probar_resumen_agua_local(self) -> None:
        try:
            df = calcular_resumen_agua()
            salida = [
                "RESUMEN AGUA LOCAL",
                "=" * 120,
                f"Variable agua          : {VARIABLE_AGUA}",
                f"Regla día operativo    : {REGLA_DIA_OPERATIVO}",
                "",
                df.to_string(index=False),
            ]

            self._mostrar_texto(
                "Resumen agua calculado localmente",
                "\n".join(salida),
                "1100x420",
            )

        except Exception as exc:
            messagebox.showerror(
                "Error",
                f"No fue posible calcular resumen local de agua.\n\n{exc}",
            )

    def probar_tendencia_agua_local(self) -> None:
        try:
            df = calcular_tendencia_agua()
            salida = [
                "TENDENCIA AGUA LOCAL",
                "=" * 140,
                f"Variable agua          : {VARIABLE_AGUA}",
                f"Regla día operativo    : {REGLA_DIA_OPERATIVO}",
                f"Filas generadas        : {len(df)}",
                "",
                df.to_string(index=False),
            ]

            self._mostrar_texto(
                "Tendencia agua calculada localmente",
                "\n".join(salida),
                "1280x520",
            )

        except Exception as exc:
            messagebox.showerror(
                "Error",
                f"No fue posible calcular tendencia local de agua.\n\n{exc}",
            )

    def _formatear_resultado_mapa_agua(self, result: dict) -> str:
        lineas = [
            "El archivo Excel fue actualizado correctamente.",
            "",
            f"Ruta:\n{result['path']}",
            "",
            f"Hoja {result['resumen_sheet']}: {result['resumen_rows']} filas",
            f"Hoja {result['tendencia_sheet']}: {result['tendencia_rows']} filas",
            f"Hoja {result['indice_sheet']}: catálogo de meses disponible",
            "",
            "Meses creados o actualizados en esta ejecución:",
        ]

        for item in result.get("monthly_sheets", []):
            lineas.append(
                f"- {item['sheet']} ({item['periodo']} | {item['estado']}): "
                f"{item['rows']} filas"
            )

        preserved = result.get("preserved_sheets", [])
        if preserved:
            lineas.extend([
                "",
                f"Meses antiguos conservados sin borrar: {len(preserved)}",
            ])

        lineas.append(
            f"Total de hojas mensuales acumuladas: "
            f"{result.get('total_monthly_sheets', 0)}"
        )

        return "\n".join(lineas)

    def generar_mapa_agua_default(self) -> None:
        try:
            result = guardar_mapa_agua_excel(DEFAULT_OUTPUT_XLSX)

            messagebox.showinfo(
                "MapaAgua generado",
                self._formatear_resultado_mapa_agua(result),
            )

        except PermissionError:
            messagebox.showerror(
                "Archivo en uso",
                "No fue posible reemplazar MapaAgua.xlsx.\n\n"
                "Cierra el archivo en Excel y vuelve a ejecutar la generación.",
            )

        except Exception as exc:
            messagebox.showerror(
                "Error",
                f"No fue posible generar MapaAgua.xlsx.\n\n{exc}",
            )

    def generar_mapa_agua_como(self) -> None:
        try:
            filename = filedialog.asksaveasfilename(
                title="Guardar MapaAgua.xlsx",
                defaultextension=".xlsx",
                initialfile="MapaAgua.xlsx",
                filetypes=[
                    ("Libro de Excel", "*.xlsx"),
                    ("Todos los archivos", "*.*"),
                ],
            )

            if not filename:
                return

            result = guardar_mapa_agua_excel(Path(filename))

            messagebox.showinfo(
                "MapaAgua generado",
                self._formatear_resultado_mapa_agua(result),
            )

        except PermissionError:
            messagebox.showerror(
                "Archivo en uso",
                "No fue posible reemplazar el archivo seleccionado.\n\n"
                "Ciérralo en Excel y vuelve a intentar.",
            )

        except Exception as exc:
            messagebox.showerror(
                "Error",
                f"No fue posible generar el archivo Excel.\n\n{exc}",
            )


    def mostrar_resumen_diario(self) -> None:
        """Muestra el resumen diario operacional 07:00-07:00."""
        nombre = self._obtener_variable()
        if nombre is None:
            return

        fecha_inicio = self.entry_inicio.get().strip()
        fecha_fin = self.entry_fin.get().strip()

        try:
            df = calcular_resumen_diario_variable(
                nombre_variable=nombre,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
            )

            salida = [
                "RESUMEN DIARIO 07:00-07:00",
                "=" * 100,
                f"Variable / equipo : {nombre}",
                f"Desde             : {fecha_inicio}",
                f"Hasta             : {fecha_fin}",
                "",
                df.to_string(index=False),
            ]

            self._mostrar_texto(
                f"Resumen diario - {nombre}",
                "\n".join(salida),
                "900x520",
            )

        except ValueError as exc:
            messagebox.showerror(
                "Rango inválido",
                str(exc),
            )

        except Exception as exc:
            messagebox.showerror(
                "Error",
                f"No fue posible calcular el resumen diario.\n\n{exc}",
            )

    def generar_resumen_diario_como(self) -> None:
        """Guarda el resumen diario operacional en Excel."""
        nombre = self._obtener_variable()
        if nombre is None:
            return

        fecha_inicio = self.entry_inicio.get().strip()
        fecha_fin = self.entry_fin.get().strip()

        nombre_limpio = (
            nombre.replace(" ", "_")
                  .replace("/", "_")
                  .replace("\\", "_")
                  .replace(":", "_")
                  .replace("*", "_")
                  .replace("?", "_")
                  .replace('"', "_")
                  .replace("<", "_")
                  .replace(">", "_")
                  .replace("|", "_")
        )

        filename = filedialog.asksaveasfilename(
            title="Guardar resumen diario",
            defaultextension=".xlsx",
            initialfile=(
                f"Resumen_Diario_{nombre_limpio}_{fecha_inicio}_{fecha_fin}.xlsx"
            ),
            initialdir=str(DEFAULT_OUTPUT_RESUMEN_DIARIO_XLSX.parent),
            filetypes=[
                ("Libro de Excel", "*.xlsx"),
                ("Todos los archivos", "*.*"),
            ],
        )

        if not filename:
            return

        try:
            result = guardar_resumen_diario_variable_excel(
                path=Path(filename),
                nombre_variable=nombre,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
            )

            messagebox.showinfo(
                "Resumen diario generado",
                "Excel generado correctamente.\n\n"
                f"Ruta:\n{result['path']}\n\n"
                f"Hoja: {result['sheet']}\n"
                f"Filas: {result['rows']}\n"
                f"Consumo total: {result['total_consumo']:,.3f}",
            )

        except PermissionError:
            messagebox.showerror(
                "Archivo en uso",
                "Cierra el archivo Excel y vuelve a intentar.",
            )

        except ValueError as exc:
            messagebox.showerror(
                "Rango inválido",
                str(exc),
            )

        except Exception as exc:
            messagebox.showerror(
                "Error",
                f"No fue posible generar el resumen diario.\n\n{exc}",
            )


    def abrir_generador_dga(self) -> None:
        """
        Abre una ventana para generar una fila diaria a una hora DGA fija.
        """
        ventana = tk.Toplevel(self.root)
        ventana.title("Reporte DGA - Pozo")
        ventana.geometry("520x330")
        ventana.resizable(False, False)

        frame = ttk.Frame(ventana, padding=20)
        frame.pack(fill="both", expand=True)

        ahora = datetime.now(TZ_CHILE)

        ttk.Label(
            frame,
            text="Fecha inicial (AAAA-MM-DD):",
        ).grid(row=0, column=0, sticky="w", pady=8)

        entry_desde = ttk.Entry(frame, width=15)
        entry_desde.grid(row=0, column=1, sticky="w", pady=8)
        entry_desde.insert(0, ahora.strftime("%Y-%m-01"))

        ttk.Label(
            frame,
            text="Fecha final (AAAA-MM-DD):",
        ).grid(row=1, column=0, sticky="w", pady=8)

        entry_hasta = ttk.Entry(frame, width=15)
        entry_hasta.grid(row=1, column=1, sticky="w", pady=8)
        entry_hasta.insert(0, ahora.strftime("%Y-%m-%d"))

        ttk.Label(
            frame,
            text="Hora de medición DGA:",
        ).grid(row=2, column=0, sticky="w", pady=8)

        combo_hora = ttk.Combobox(
            frame,
            state="readonly",
            width=8,
            values=[f"{h:02d}" for h in range(24)],
        )
        combo_hora.grid(row=2, column=1, sticky="w", pady=8)
        combo_hora.set(f"{DGA_HORA_DEFAULT:02d}")

        ttk.Label(
            frame,
            text=(
                "Se utilizará la primera lectura real disponible después "
                "de la hora elegida.\n"
                "El caudal se calcula con la variación del totalizador "
                "durante aproximadamente 1 hora."
            ),
            foreground="gray",
            justify="left",
        ).grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(12, 16),
        )

        def generar() -> None:
            fecha_inicio = entry_desde.get().strip()
            fecha_fin = entry_hasta.get().strip()

            try:
                datetime.strptime(fecha_inicio, "%Y-%m-%d")
                datetime.strptime(fecha_fin, "%Y-%m-%d")
                hora = int(combo_hora.get())
            except ValueError:
                messagebox.showerror(
                    "Datos inválidos",
                    "Revisa las fechas y la hora seleccionada.",
                )
                return

            filename = filedialog.asksaveasfilename(
                title="Guardar reporte DGA",
                defaultextension=".xlsx",
                initialfile=(
                    f"DGA_Pozo_{fecha_inicio}_{fecha_fin}.xlsx"
                ),
                initialdir=str(DEFAULT_OUTPUT_DGA_XLSX.parent),
                filetypes=[
                    ("Libro de Excel", "*.xlsx"),
                    ("Todos los archivos", "*.*"),
                ],
            )

            if not filename:
                return

            try:
                result = guardar_reporte_dga_excel(
                    path=Path(filename),
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    hora_medicion=hora,
                )

                messagebox.showinfo(
                    "Reporte DGA generado",
                    (
                        "Archivos generados correctamente.\n\n"
                        f"Reporte DGA:\n{result['path']}\n\n"
                        f"Trazabilidad:\n{result['trazabilidad_path']}\n\n"
                        f"Días: {result['rows']}\n"
                        f"Con totalizador: {result['con_totalizador']}\n"
                        f"Con caudal calculado: {result['con_caudal']}\n"
                        f"Con nivel freático: {result['con_nivel']}\n"
                        f"Hora DGA: {result['hora_medicion']:02d}"
                    ),
                )

                ventana.destroy()

            except PermissionError:
                messagebox.showerror(
                    "Archivo en uso",
                    "Cierra el archivo Excel y vuelve a intentar.",
                )

            except Exception as exc:
                messagebox.showerror(
                    "Error",
                    f"No fue posible generar el reporte DGA.\n\n{exc}",
                )

        ttk.Button(
            frame,
            text="Generar Excel DGA",
            command=generar,
            width=24,
        ).grid(
            row=4,
            column=0,
            columnspan=2,
            pady=10,
        )



def run_app() -> None:
    root = tk.Tk()
    TelemetryApp(root)
    root.mainloop()
