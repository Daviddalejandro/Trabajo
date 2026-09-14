# Ejecución en Google Colab (sin instalar nada)

`MDM_Prototipo_Colab.ipynb` levanta el prototipo completo en una máquina temporal de Google: instala PostgreSQL 16,
crea la base, siembra el RDM, carga el conjunto de datos elegido (validación SAP ECC + crédito, o los 20 casos demo),
arranca la API sirviendo la consola compilada (`colab/ui/`, un solo puerto) y muestra el enlace para abrirla en el
navegador mientras el cuaderno esté en ejecución.

| Archivo | Uso |
|---|---|
| `MDM_Prototipo_Colab.ipynb` | El cuaderno. Copia en Drive: `MDM_RDM_Prototipo/08_Colab/`. Abrir con Colab y *Ejecutar todo*. |
| `build_notebook.py` | Genera el cuaderno; editar aquí y volver a ejecutar para cambiarlo (revisable en Git). |
| `ui/` | Consola compilada con `VITE_API_BASE=/api/v1` (base relativa). Se regenera con `make ui-colab`. |

Origen del código en el cuaderno: `drive` (zip `MDM_RDM_Prototipo/08_Colab/mdm-rdm-prototype.zip`, sin credenciales) o
`github` (clona la rama; si el repositorio es privado requiere un token de acceso personal). El zip se genera con
`make zip-colab` y hay que volver a subirlo a Drive tras cada cambio de código.

Limitaciones de Colab: la máquina se borra al cerrar o por inactividad (~90 min sin uso); los resultados que se
quieran conservar se guardan en Drive con la sección 7 del cuaderno. El enlace de la consola solo funciona para la
cuenta que ejecuta el cuaderno (proxy de Colab).
