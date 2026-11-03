# Consulta tus leyes

Aplicación web local basada en el diseño de Figma de «Consulta tus leyes». Incluye frontend responsive, API y persistencia real en SQLite. **El catálogo legislativo es una demostración con 24 fichas ficticias: 8 leyes y 16 proyectos. No está conectado al Congreso.**

## Iniciar en Windows y VS Code

1. Abra `Consulta tus leyes.code-workspace` con VS Code, o abra esta carpeta desde **Archivo → Abrir carpeta**.
2. En **Terminal → Nueva terminal**, ejecute:

   ```powershell
   python backend/server.py
   ```

3. Abra **http://127.0.0.1:8000** en su navegador. Mantenga la terminal abierta.
4. Para detener el servidor, pulse **Ctrl+C** en esa terminal.

También puede hacer doble clic en `iniciar.bat`, o usar **Terminal → Ejecutar tarea → Iniciar Consulta tus leyes**. No requiere npm, pip, instalación de base de datos ni claves de API. Requisito: Python 3.10 o superior con SQLite (incluido en la instalación habitual).

Si Windows no reconoce `python`, pruebe `py -3 backend/server.py`. Si el puerto está ocupado, detenga la ejecución anterior o use `python backend/server.py --port 8001` y abra http://127.0.0.1:8001. Use siempre el mismo host (127.0.0.1 o localhost) para conservar la sesión.

## Recorridos disponibles

- Dos pantallas de bienvenida con GIF, pausa y alternativa estática para movimiento reducido.
- Registro con validación, confirmación de contraseña y condiciones; inicio y cierre de sesión.
- Acceso de visitante con nombre e intereses opcionales. Al crear una cuenta desde esa sesión, los guardados y seguimientos se trasladan a la cuenta.
- Inicio por situaciones cotidianas; búsqueda por número, palabras o sinónimos asociados a temas.
- Resultados y filtros combinados por tipo, sector, estado, cámara de origen, grupo, autor, comisión, objetivo del Acuerdo Nacional y fechas.
- Fichas de ley y proyecto, texto descargable, cronología de ejemplo, valoración de claridad y enlace relacionado.
- Guardados y seguimientos persistidos por usuario, disponibles desde «Mi espacio».
- Estadísticas calculadas sobre la selección actual y exportación CSV/JSON.
- Opiniones: una respuesta modificable por cuenta y proyecto. Comentarios pendientes visibles solo para su autor.
- Mensajes de éxito con GIF, íconos con ampliación al pasar el mouse, foco de teclado y diseño adaptable.

Las fuentes, íconos y GIF están incluidos localmente: una vez descargado el proyecto, no se necesita conexión para usarlo. Los enlaces externos a fuentes oficiales sí requieren Internet.

## Código y datos

```text
frontend/
  index.html          Entrada de la aplicación
  styles.css          Colores, tipografía, componentes y responsive
  js/app.js           Pantallas, navegación y eventos
  js/api.js           Cliente de la API y sesión en memoria
  js/ui.js            Componentes y utilidades de presentación
  assets/             SVG de Figma, GIF, PNG y tipografías
backend/
  server.py           Servidor HTTP, API, autenticación y archivos estáticos
  database.py         Tablas SQLite y conexión
  catalog.py          Catálogo sintético, buscador y estadísticas
data/consulta.db      Se crea automáticamente al iniciar (ignorada por Git)
tests/test_api.py     Pruebas de integración con una base temporal
.vscode/             Tareas, depuración y extensiones sugeridas
```

El navegador y la API comparten origen; no abra `index.html` directamente ni use Live Server. El backend también sirve los archivos del frontend.

## API

Las respuestas son JSON salvo las descargas. Los errores incluyen `error` y un estado HTTP apropiado.

| Ruta | Método | Función |
| --- | --- | --- |
| `/api/health`, `/api/meta`, `/api/session` | GET | Estado, catálogos de filtros y sesión |
| `/api/register`, `/api/login`, `/api/guest` | POST | Acceso y creación de sesión |
| `/api/logout` | POST | Cierre de sesión |
| `/api/documents` | GET | Catálogo filtrado |
| `/api/documents/DEMO-001` | GET | Ficha y guardados del usuario |
| `/api/documents/DEMO-001/text` | GET | Texto de ejemplo descargable |
| `/api/bookmarks` | GET / POST / DELETE | Lista, guarda o retira una ficha |
| `/api/documents/DEMO-002/opinion` | GET / POST | Resultados y respuesta del usuario |
| `/api/documents/DEMO-002/comments` | POST | Comentario pendiente |
| `/api/documents/DEMO-001/feedback` | POST | Claridad de la explicación |
| `/api/stats`, `/api/policies` | GET | Estadísticas y objetivos |
| `/api/export?format=csv` o `json` | GET | Descarga de la selección |

Filtros: `q`, `kind=ley|proyecto`, `sector`, `status`, `chamber`, `group`, `author`, `commission`, `policy`, `from=AAAA-MM-DD`, `to=AAAA-MM-DD`. Los valores disponibles se consultan en `/api/meta`. Cada ficha se cuenta una vez; cámara y grupo corresponden al origen. No se calcula una tasa de aprobación.

Los cambios privados requieren cookie de sesión y cabecera `X-CSRF-Token`, obtenida en `/api/session`. El frontend se encarga de enviarlas. Las contraseñas se derivan con PBKDF2-SHA256, 600 000 iteraciones y sal aleatoria. Las cookies son HttpOnly y SameSite Strict; los tokens se guardan como hash en la base. La sesión de cuenta vence en siete días y la de visitante en 24 horas. No se guardan credenciales en localStorage.

## Pruebas y depuración

Desde esta carpeta:

```powershell
python -m unittest discover -s tests -v
```

Las pruebas levantan un servidor temporal en un puerto libre; no usan ni modifican `data/consulta.db`. Verifican búsqueda, filtros, totales, exportación, autenticación, CSRF, aislamiento de usuarios, migración del visitante, voto único, privacidad de comentarios y acceso a archivos.

Para depurar con F5 seleccione **Backend Python + frontend**. Requiere las extensiones oficiales Python y Python Debugger de Microsoft; están sugeridas en el proyecto. Ejecutar normalmente en la terminal no requiere extensiones.

## Alcance y siguiente etapa

Esta entrega es funcional para desarrollo local. Se enlaza exclusivamente a 127.0.0.1. No se diseñó como servidor de producción ni debe exponerse directamente a Internet.

Para una versión pública quedan: integración validada con fuentes legislativas oficiales y sus identificadores; actualización y trazabilidad de datos; revisión jurídica de resúmenes; HTTPS y servidor de aplicación de producción; verificación de correo y recuperación de contraseña; servicio de avisos; moderación administrativa; política institucional de privacidad y conservación. No existe recuperación de contraseña, envío de correo, IA generativa ni publicación automática de comentarios en esta versión.

Los intereses del visitante se guardan como preferencias de sesión; no modifican los resultados de forma oculta. Los filtros son explícitos. «Acuerdo Nacional» utiliza cuatro objetivos como clasificación temática ilustrativa, no como evidencia de alineamiento oficial.

Para ensayar sin afectar sus datos, use otra base: `python backend/server.py --port 8001 --db data/pruebas.db`. Para reiniciar una instalación, detenga el servidor y archive o cambie el nombre de su archivo SQLite antes de volver a iniciarlo. No elimine una base que contenga información que desee conservar.

## Diseño y recursos

Referencia: https://www.figma.com/design/b6AmLnWHATfNxVuJfUZJIw/Consulta-tus-leyes

Colores y jerarquías: guinda #9A0000, fondo #F5F4F2, texto #2C2A2B; Montserrat para títulos e IBM Plex Sans para cuerpo. Las tipografías incluyen su licencia SIL Open Font License en `frontend/assets/fonts/`. SVG obtenidos del archivo Figma del proyecto; GIF provenientes de los recursos de onboarding del mismo proyecto. La adaptación conserva el diseño móvil y centra la aplicación en pantallas grandes.
