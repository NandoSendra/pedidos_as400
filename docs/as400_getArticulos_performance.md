# Ajuste de salida `getArticulos`

## Problema principal: líneas no rellenadas

Si `salida.articulos` está definido en la estructura `Respuesta` como un array fijo, por ejemplo `DIM(9999)`, IBM i Integrated Web Services puede devolver todas las posiciones del array aunque solo se hayan rellenado `contador` artículos.

Además, esta línea también toca todo el array fijo:

```rpgle
clear salida;
```

Si `Respuesta` contiene `articulos DIM(9999)`, ese `clear` inicializa las 9999 posiciones. Aunque luego solo rellenes 23, el programa ya ha limpiado todo el bloque de artículos.

En el RPG ya se informa el número real:

```rpgle
lineas_salida = contador;
salida.numArticulos = contador;
```

Pero eso solo sirve si el web service usa `lineas_salida` o `salida.numArticulos` como contador del array. Si en la configuración del servicio el array tiene Count = `9999`, el JSON incluirá también las líneas vacías.

### Cambio recomendado en IWS

En el despliegue/configuración del servicio, el parámetro/array `articulos` debe tener el Count enlazado a un campo entero de salida, no a un literal fijo.

Usar:

```text
Count = lineas_salida
```

o, si el asistente permite seleccionar el campo interno:

```text
Count = salida.numArticulos
```

Evitar:

```text
Count = 9999
```

La idea es que el web service serialice solo las posiciones `1..contador`.

IBM documenta que los arrays de dimensión variable se controlan con `%ELEM`, pero también indica restricciones importantes: no se pueden usar como subcampos ni directamente como parámetros de procedimiento en todos los casos. Por eso, para IWS suele ser más práctico usar el contador de array en el despliegue del servicio.

Como defensa adicional, el cliente Python filtra artículos sin `codigo`, pero eso ocurre después de que AS/400 ya haya enviado el JSON. Para reducir realmente la carga, hay que corregir el Count en AS/400/IWS.

## Cambio recomendado en RPG

Si el Count del array queda bien configurado en IWS, evita limpiar toda la estructura de salida. Inicializa solo la cabecera:

```rpgle
// Evitar: clear salida;
salida.success = *on;
salida.numArticulos = 0;
lineas_salida = 0;
```

Y al rellenar un artículo, limpia solo la posición que vas a usar:

```rpgle
contador += 1;

clear salida.articulos(contador);
salida.articulos(contador).codigo = %trim(art);
salida.articulos(contador).descripcion = %trim(%char(ARNBR));
// resto de campos...
```

Al final:

```rpgle
lineas_salida = contador;
salida.numArticulos = contador;
```

Importante: si el servicio sigue serializando `DIM(9999)`, no conviene quitar `clear salida`, porque podrían aparecer datos antiguos en las posiciones no rellenadas. Primero corrige el Count del array en IWS; después puedes evitar el `clear salida` completo.

## Mejora adicional: no construir histórico completo

El procedimiento actual recibe `fechaAnalisis`, pero la lista inicial de artículos se construye desde `fecdes = 19990101`:

```rpgle
if prv > 0;
    OBTMOVHCD(prv:fecdes:gArryArt:NumArt);
else;
    chain 1 rgfcpcf;
    OBTMOVTM(cfcar:fecdes:gArryArt:NumArt);
endif;
```

Después se filtra cada artículo:

```rpgle
setgt art rgalmhd;
readpe art rgalmhd;
if %eof(almhdlb) or hdfch <= fechaAnalisis;
    iter;
endif;
```

Eso hace que aunque la salida final sean pocos artículos, AS/400 haya recorrido la carga completa histórica.

## Cambio recomendado

Usar `fechaAnalisis` ya en la búsqueda inicial:

```rpgle
if prv > 0;
    OBTMOVHCD(prv:fechaAnalisis:gArryArt:NumArt);
else;
    chain 1 rgfcpcf;
    OBTMOVTM(cfcar:fechaAnalisis:gArryArt:NumArt);
endif;
```

Mantener el filtro posterior es correcto como protección:

```rpgle
if %eof(almhdlb) or hdfch <= fechaAnalisis;
    iter;
endif;
```

## Efecto

La carga deja de construir `gArryArt` con todos los artículos desde 1999 y pasa a crear la lista solo con movimientos posteriores a `fechaAnalisis`. El resultado funcional debe ser el mismo para la pantalla normal, pero el coste baja mucho cuando hay pocos artículos recientes.

El modo "todos" puede seguir enviando una fecha antigua si realmente se quiere una carga completa.
