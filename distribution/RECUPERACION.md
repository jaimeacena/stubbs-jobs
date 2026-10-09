# Copias, recuperación y actualización

## Crear una copia

1. Guarda los cambios pendientes en Mi perfil o en la solicitud que estés editando.
2. Abre **Copias de seguridad** en el menú y pulsa **Crear copia de seguridad**.
3. La app comprueba que el registro, los CV y los materiales conservados coincidan con sus originales. Si falta un archivo, explica cuál necesita recuperar.
4. Pulsa **Descargar copia** y conserva el ZIP en una ubicación que controles. También queda una copia en `data/backups`.

La copia contiene datos personales, documentos e historial. No contiene contraseñas, la sesión del navegador ni el acceso a los portales. Los borradores que todavía no has guardado en la app permanecen en ese navegador; guárdalos antes de preparar la copia.

## Recuperar los datos

En **Copias de seguridad** puedes copiar una petición para que el agente compruebe y recupere la copia. Si ya tienes un ZIP de otra carpeta, indica su ubicación en ese chat.

El agente debe comprobar la copia, recuperarla en una carpeta nueva fuera de la instalación actual y comparar el perfil, los CV, las ofertas, las solicitudes y los cambios posteriores. No admite una subcarpeta de esa instalación ni una carpeta que la contenga. La instalación actual se conserva. Si falla una comprobación, se conservan los archivos para revisarlos; no se presenta la copia como lista para utilizar. El acceso habitual de apertura se añade únicamente después de completar las comprobaciones, retirar los permisos antiguos y guardar la guía de recuperación.

La recuperación mantiene los hechos y las pruebas originales. Los permisos antiguos de envío se retiran y las selecciones automáticas vuelven al modo con revisión. El trabajo que estaba ejecutándose queda pendiente de comprobar. Una solicitud enviada conserva su confirmación. Una solicitud interrumpida exige comprobar el portal antes de repetir cualquier acción. `data/recovery-original.json` conserva el registro completo anterior a estas medidas de recuperación.

Antes de utilizar la carpeta recuperada, revisa con el agente las diferencias respecto a la instalación actual. Abre esa carpeta en un chat con acceso a sus archivos y comprueba el estado. No utilices dos copias para enviar solicitudes del mismo proceso.

## Actualizar y poder volver atrás

1. Termina o aclara el trabajo en curso y guarda los borradores.
2. Crea y comprueba una copia de seguridad.
3. Descomprime la nueva versión en otra carpeta. Conserva la anterior.
4. Pide al agente que recupere los datos con el código nuevo, compruebe el estado y compare ambas instalaciones antes de sustituir nada.
5. Comprueba que aparecen tu perfil, CV, ofertas, solicitudes y sus pruebas. Los envíos pendientes necesitan revisión y permiso actuales.

Para volver a una versión anterior, conserva primero una copia de los datos actuales. El agente debe comprobar que el código anterior admite esos datos y conciliar los cambios posteriores. Recuperar una copia antigua sin esa comparación puede omitir trabajo reciente. No existe un actualizador automático.

## Procedimiento del agente

Utiliza exclusivamente el escritor oficial:

```text
python tools/stubbs_jobs.py backup
python tools/stubbs_jobs.py check-backup --file COPIA.zip
python tools/stubbs_jobs.py restore --file COPIA.zip --destination CARPETA_NUEVA
```

`restore` comprueba todas las huellas y rutas antes de crear la carpeta. Recupera el código de la instalación que ejecuta el comando y los datos comprobados del ZIP. El código del ZIP nunca se ejecuta. El ajuste de permisos y tareas pasa por una operación del escritor en la copia aislada. No modifica el registro de la carpeta original, no inicia búsquedas y no envía solicitudes.
