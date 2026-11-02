import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.backends.backend_pdf import PdfPages
import textwrap

class SurveyManager:
    @staticmethod
    def procesar_excel(ruta_excel):
        """Extrae y limpia los datos del Excel."""
        try:
            df = pd.read_excel(ruta_excel, engine='openpyxl')
        except Exception as e:
            raise Exception(f"Falla al leer el archivo: {e}")

        nuevas_columnas = [
            "fecha_marca_temporal", "nivel_diversion", "peor_parte_estudiar",
            "motivacion_aprendizaje", "tipo_juegos_preferidos", 
            "quiere_gamificacion", "idea_juego_inventado"
        ]

        if len(df.columns) != len(nuevas_columnas):
            raise Exception("El formato de las columnas no coincide con la base de datos.")

        df.columns = nuevas_columnas
        df.fillna("Sin respuesta", inplace=True)
        return df

    @staticmethod
    def exportar_pdf(df, ruta_guardado):
        """Toma el DataFrame y escupe el reporte en PDF con todas las gráficas."""
        if df.empty:
            raise Exception("No hay datos para exportar.")
            
        with PdfPages(ruta_guardado) as pdf:
            def formatear_etiquetas(etiquetas, ancho=30):
                return [textwrap.fill(e.get_text(), width=ancho) for e in etiquetas]

            # 1. Diversión
            if 'nivel_diversion' in df.columns:
                fig1, ax1 = plt.subplots(figsize=(10, 6))
                sns.countplot(data=df, y='nivel_diversion', order=df['nivel_diversion'].value_counts().index, palette='viridis', ax=ax1)
                ax1.set_title("1. ¿Qué tan divertido es aprender en el colegio?", fontsize=14, pad=15)
                ax1.set_xlabel("Cantidad de Alumnos")
                ax1.set_ylabel("")
                ax1.set_yticklabels(formatear_etiquetas(ax1.get_yticklabels()))
                plt.tight_layout()
                pdf.savefig(fig1)
                plt.close(fig1)

            # 2. Peor parte
            if 'peor_parte_estudiar' in df.columns:
                fig2, ax2 = plt.subplots(figsize=(10, 6))
                sns.countplot(data=df, y='peor_parte_estudiar', order=df['peor_parte_estudiar'].value_counts().index, palette='rocket', ax=ax2)
                ax2.set_title("2. Lo peor de estudiar es...", fontsize=14, pad=15)
                ax2.set_xlabel("Cantidad de Alumnos")
                ax2.set_ylabel("")
                ax2.set_yticklabels(formatear_etiquetas(ax2.get_yticklabels()))
                plt.tight_layout()
                pdf.savefig(fig2)
                plt.close(fig2)

            # 3. Motivación
            if 'motivacion_aprendizaje' in df.columns:
                fig3, ax3 = plt.subplots(figsize=(10, 6))
                sns.countplot(data=df, y='motivacion_aprendizaje', order=df['motivacion_aprendizaje'].value_counts().index, palette='mako', ax=ax3)
                ax3.set_title("3. Si vas a aprender algo, que sea porque...", fontsize=14, pad=15)
                ax3.set_xlabel("Cantidad de Alumnos")
                ax3.set_ylabel("")
                ax3.set_yticklabels(formatear_etiquetas(ax3.get_yticklabels()))
                plt.tight_layout()
                pdf.savefig(fig3)
                plt.close(fig3)

            # 4. Tipo de juegos
            if 'tipo_juegos_preferidos' in df.columns:
                fig4, ax4 = plt.subplots(figsize=(10, 6))
                sns.countplot(data=df, y='tipo_juegos_preferidos', order=df['tipo_juegos_preferidos'].value_counts().index, palette='crest', ax=ax4)
                ax4.set_title("4. ¿Qué tipo de juegos/actividades son más tu estilo?", fontsize=14, pad=15)
                ax4.set_xlabel("Cantidad de Alumnos")
                ax4.set_ylabel("")
                ax4.set_yticklabels(formatear_etiquetas(ax4.get_yticklabels()))
                plt.tight_layout()
                pdf.savefig(fig4)
                plt.close(fig4)

            # 5. Gamificación (Torta)
            if 'quiere_gamificacion' in df.columns:
                fig5, ax5 = plt.subplots(figsize=(8, 8))
                gam_counts = df['quiere_gamificacion'].value_counts()
                etiquetas_formateadas = [textwrap.fill(str(idx), 20) for idx in gam_counts.index]
                ax5.pie(gam_counts, labels=etiquetas_formateadas, autopct='%1.1f%%', startangle=140, colors=sns.color_palette("pastel"))
                ax5.set_title("5. ¿Te gustaría que aprender fuera con apps/juegos?", fontsize=14, pad=15)
                plt.tight_layout()
                pdf.savefig(fig5)
                plt.close(fig5)
            
            # 6. Juegos Inventados (Limpieza)
            if 'idea_juego_inventado' in df.columns:
                juegos_separados = df['idea_juego_inventado'].dropna().astype(str).str.split(',').explode().str.strip()
                juegos_separados = juegos_separados[juegos_separados != ""]
                juegos_separados = juegos_separados[~juegos_separados.isin(["Sin respuesta", "nan", "None"])] 
                
                if not juegos_separados.empty:
                    top_juegos = juegos_separados.value_counts().head(10)
                    fig6, ax6 = plt.subplots(figsize=(10, 6))
                    sns.barplot(x=top_juegos.values, y=top_juegos.index, palette='magma', ax=ax6)
                    ax6.set_title("6. Top 10 Mecánicas/Juegos Más Mencionados", fontsize=14, pad=15)
                    ax6.set_xlabel("Frecuencia de Mención")
                    ax6.set_ylabel("")
                    ax6.set_yticklabels(formatear_etiquetas(ax6.get_yticklabels(), 40))
                    plt.tight_layout()
                    pdf.savefig(fig6)
                    plt.close(fig6)