# Línea de tiempo detallada · Neon OS

Este documento cuenta, en orden, cómo se construyó Neon OS: qué hicimos en cada etapa, qué archivos del código nacieron ahí y qué
aprendimos antes de pasar a la siguiente.

[← Volver al README](../README.md)

| Año | Grado | Luis Enrique Barreto Duarte | Daniel Santiago Sandoval Torres |
|---|---|---|---|
| 2024 | Noveno | 907 | 905 |
| 2025 | Décimo | 1002 | 1005 |
| 2026 | Once | 1102 | 1105 |

---

## Antecedentes · El estadio de matrices LED (marzo – julio de 2024)

- Alrededor del **20 de marzo de 2024**, durante el **servicio social** de noveno (Luis en 907 y Daniel en 905), tuvimos la primera idea: un **estadio de fútbol con matrices LED**
  muy grandes y totalmente programadas.
- Trabajamos en ella unos **cuatro meses**. La descartamos porque **costaba demasiado dinero**.
- Después pensamos en un proyecto hecho **únicamente con bases de datos SQL**, construidas al 100 % por nosotros. También lo descartamos,
  porque era **demasiado pesado**. Por eso nos quedamos con una aplicación educativa más sencilla y viable.

## Etapa 0 · Arranque (12 de febrero de 2025)

- Inicio oficial del proyecto en la Especialización de Tecnología (en décimo: Luis en 1002 y Daniel en 1005; docente Juan Camilo Rodríguez Montes), con
  Daniel Santiago Sandoval Torres y Luis Enrique Barreto Duarte.
- La aplicación empezó como **Educational Arcade Project**, su nombre más conocido. Después pasó a llamarse **Arcade Game**, luego
  **Arcade National** y, por último, **Neon Builders**. La app quedó como **Neon OS**.
- Lema: *«Con luz y saber, jugamos para crecer»*.

## Etapa 1 · Empatizar (julio – octubre de 2025)

**Observación (julio a septiembre).** Registramos diez situaciones reales en el colegio:

| # | Situación | Lugar |
|---|---|---|
| 1 | Un estudiante de décimo ve videos en la sala de tecnología | Sala de tecnología, 3.er piso |
| 2 | Un estudiante se duerme en Ciencias (grado sexto) | Salón 609 |
| 3 | Un estudiante revisa redes en Tecnología (grado noveno) | Salón de artes, Torre Nueva |
| 4 | Un estudiante juega videojuegos en la especialización | Salón de especialización |
| 5 | Un estudiante duerme en el espacio de Prueba Saber | Salón 1002 |
| 6 | Un estudiante usa el celular en vez de hacer Química | Salón 1005 |
| 7 | Un estudiante habla para no dejar empezar la clase de Física | Salón 1005 |
| 8 | Un estudiante de décimo «capa» la clase de Sociales | Patio azul, sección nueva |
| 9 | Estudiantes de noveno juegan Brawl Stars en Inglés | Salón 903 |
| 10 | Estudiantes de quinto conversan en vez de atender en Sistemas | Sala del 5.º piso, Torre Nueva |

**Encuesta (2 al 22 de octubre de 2025).** La encuesta *«Aprendizaje y motivación escolar»*, hecha en Google Forms, tuvo 75 respuestas.
Los resultados están en [ENCUESTA.md](ENCUESTA.md).

**Hallazgo clave:** la atención no desaparece, se va hacia lo que da reto y recompensa inmediata.

## Etapa 1.1 · Definir (noviembre de 2025)

- Hicimos el mapa de causas y efectos de las tres problemáticas: el colegio no divierte, no entienden los temas y se refugian en el celular.
  Las tres tienen la misma raíz: **la forma de enseñar desmotiva**.
- **Enunciado:** los estudiantes de décimo y once necesitan una forma de estudiar dinámica, con retos, recompensas y explicaciones
  inmediatas, porque perdieron la motivación con los métodos tradicionales.
- **Pregunta:** ¿Cómo podríamos cambiar el método de aprendizaje convirtiendo el repaso en un juego con retos, recompensas y
  retroalimentación?

## Etapa 2 · Idear (noviembre de 2025 – febrero de 2026)

- Taller 8: respondimos las cinco preguntas pertinentes.
- Lluvia de 12 ideas: Neon OS, Quiz Royale, EscapeClass, ChemLab Mix, Math Invaders, StoryVerse, Duel Mind, un bot de WhatsApp, un tablero
  físico de puntos, videos cortos, tutorías entre pares y un modo foco.
- Mapa de empatía (decir, pensar, hacer, sentir) y agrupación en cuatro cuadrantes. El filtrado se hizo con el taller 11.
- **Elegimos Neon OS** como plataforma para reunir las mejores ideas.

## Etapa 3 · Prototipo v0.1 (1.ª y 2.ª semana de marzo de 2026)

| Pieza | Archivo |
|---|---|
| Inicio de sesión con roles y base de datos | `base_de_datos_interfaz_de_inicio.py` |
| Materias, colores y contenido por tema | `Materias.py` |
| Vistas de estudiante, profesor y administrador | `estudiante.py`, `profesor.py`, `administrador.py` |
| Análisis de la encuesta (Excel → base de datos → PDF) | `Encuesta.py` |
| Prototipo móvil | `app_movil.py` (Flet) |

Del prototipo salieron el Mercado, la Tienda, los avatares, las vidas, la racha y la primera «Arena AI» de quizzes.
La regla de diseño que nos guió fue separar **la interfaz** de **la base de datos**.

**Ronda de pruebas 1 (abril – junio de 2026).** Ya en once, probaron la app compañeros de 1102 y 1105 y docentes de la especialización.
Nos dijeron que «se ve como un juego de verdad», pero también que tenía pocas actividades, que el progreso se perdía al cerrar y que el
profesor no podía crear sus propios retos.

## Etapa 3.1 · Versión 1.0 (1.ª y 2.ª semana de julio de 2026)

| Mejora | Archivo |
|---|---|
| Aplicación unificada | `APP_final.py` |
| Banco de grado 11: 6 materias, 30 temas y 721 actividades | `banco_grado11.py` |
| 8 minijuegos | `juegos.py` |
| Tutor con IA local (Ollama) y modo básico | `ia_local.py` |
| Usuarios, misiones y progreso persistentes | `almacen.py` |
| Rutas de la app, para que funcione desde cualquier carpeta | `rutas.py` |

**Ronda de pruebas 2 (agosto – septiembre de 2026)** y **entrega del proyecto el 29 de septiembre de 2026**.

## Etapa 3.2 · Versión 2.0 (1.ª y 2.ª semana de octubre de 2026)

| Mejora | Archivo |
|---|---|
| 421 explicaciones al fallar y felicitaciones al acertar | `juegos.py`, `banco_grado11.py` |
| Ranking solo top 10, con tarjeta de «te faltan N puntos» | `almacen.py`, `APP_final.py` |
| Arena: duelo contra un robot, 5 corazones por día | `arena.py`, `juegos.py` |
| Serpiente y Tetris con récord | `serpiente.py`, `tetris.py` |
| Verificación de correo, código de profesor y administradores | `verificacion.py`, `correo.py` |
| Configuración segura en `.env` | `entorno.py`, `.env.example` |
| Logo, ícono y ejecutable | `preparar_logo.py`, `construir_exe.ps1` |
| Diseño de la nube (Supabase) | `nube/sql/001_esquema.sql` |
| 470 pruebas automáticas | `pruebas_*.py` |

## Etapa 4 · Emprender y documentar (octubre – noviembre de 2026)

- Hicimos el modelo Canvas, los costos (piloto de ≈ $190.000 COP por periodo) y un plan de implementación en cuatro fases.
- Llenamos el formato oficial de Design Thinking y publicamos este repositorio.
