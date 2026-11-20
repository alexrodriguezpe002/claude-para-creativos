# Cómo funciona la descarga (para explicarlo o responder dudas)

## La idea
Una tarjeta se formatea solo cuando hay **dos copias en dos discos distintos** y **cada copia se comprobó
leyéndola de nuevo**. Copiar y mirar que el tamaño coincida no alcanza: un cable flojo, un disco que empieza a
fallar o un lector malo pueden dejar un archivo del mismo tamaño con bytes cambiados.

## Los pasos de cada archivo
1. Se lee **una vez** de la tarjeta. Mientras se lee, se calcula su huella (MD5) y se escribe en todos los discos
   a la vez (un hilo por disco).
2. Cada copia se escribe con un nombre temporal (`.<archivo>.parcial-descarga`) y se fuerza a disco.
3. Cada copia se **vuelve a leer desde su disco** (en Mac, con la memoria intermedia apagada: `F_NOCACHE`) y se
   compara su huella con la de la tarjeta. Si no coincide, se copia otra vez; si vuelve a fallar, ese disco o su
   cable están mal y la copia se detiene.
4. Recién entonces la copia recibe su nombre final y queda anotada en `_DESCARGA/estado.jsonl`.
5. Al terminar, se vacía la memoria interna de cada disco (`F_FULLFSYNC` en Mac) y se escriben el manifiesto y el
   informe. Recién ahí aparece el ✅.

## Por qué MD5
Es la huella que leen todos los programas de DIT (Hedge, OffShoot, ShotPut, Silverstack, el clonador de
DaVinci) y viene con Python, sin instalar nada. Velocidad medida en una Mac M1 Pro: MD5 660 MB/s, SHA-1 730 MB/s
por núcleo; un lector USB común de tarjetas SD da 90–300 MB/s y un disco rígido 150–250 MB/s, así que la huella
no frena la copia. xxHash (el que usan por defecto OffShoot y Hedge) es más rápido pero no viene con Python: para
**verificar** manifiestos con xxHash se puede instalar el módulo `xxhash` (ver la skill `verificar-material`).
Velocidad real de prueba (M1 Pro, tarjeta exFAT simulada, 2 destinos en el mismo SSD): 2,5 GB copiados y
verificados en 12 s; 300 fotos de 1 MB en 2,5 s.

## Seguir si se corta
Cada archivo verificado queda anotado al instante. Si se corta (tarjeta afuera, disco lleno, compu apagada), al
correr el mismo comando: se borran solo los temporales a medias, se saltan los archivos ya verificados y se sigue.
Si la cámara grabó más clips en la misma tarjeta (sin formatear), se copian solo los nuevos en la misma carpeta y
se escribe un manifiesto nuevo con todo.

## Nunca pisar
- Cada tarjeta va a su propia carpeta. Si ya hay otra tarjeta con el mismo nombre, la nueva va a `A001_2`.
- Si en la carpeta ya existe un archivo sin anotar: si es idéntico se adopta; si es distinto, no se toca y se
  avisa (se resuelve con `--apartar-conflictos`, que lo renombra a `.DISTINTO_<fecha>`, o a mano).
- `reparar` (verificar-material) cambia un archivo dañado por el bueno y deja el dañado como `.DANADO_<fecha>`.

## Manifiestos
- Se escribe **MHL 1.1** (`<TARJETA>_<fecha>.mhl` en la raíz de la carpeta de la tarjeta): tamaño, fecha y huella
  de cada archivo. Lo abren ShotPut, Silverstack, Hedge/OffShoot y DaVinci.
- Se leen MHL 1.1 y **ASC MHL** (carpeta `ascmhl/`, el formato nuevo de OffShoot y Silverstack), con huellas MD5,
  SHA-1 y C4; xxHash solo con el módulo `xxhash`.

## Estructuras de tarjeta que reconoce
Sony XAVC (`PRIVATE/M4ROOT`), Sony XDCAM/FX (`XDROOT`), Canon Cinema EOS (`CONTENTS/CLIPS001`), Panasonic P2
(`CONTENTS/CLIP`), AVCHD (`PRIVATE/AVCHD`), carpeta `CLIP`, RED (`.RDM`/`.R3D`), Blackmagic (`.braw`),
`DCIM` (cámaras de fotos, celulares, drones, GoPro) y grabadoras de audio (`.wav`). Lo que no reconoce igual se
puede copiar indicando la carpeta.

## Lo que se ignora
La basura que crean las computadoras en las tarjetas: `.Spotlight-V100`, `.fseventsd`, `.Trashes`, `._*`,
`System Volume Information`, `$RECYCLE.BIN`, `Thumbs.db`, `.DS_Store`.
