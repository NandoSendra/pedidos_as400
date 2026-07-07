# POST `/asientos/crear` — programa RPG e implementación en IWS

Guía para publicar en el AS/400 el endpoint que consume la app Flask (`as400_api.crear_asiento_contable`).

> **Si ya tienes un SRVPGM NOMAIN** con `getArticulos`, `crearPedido`, etc., usa
> `docs/crear_asiento_export.rpgle` (procedimiento `crearAsiento export`) en lugar
> del programa `IAERPCAS` separado. El patrón debe ser **igual que `crearPedido`**.

## Contrato JSON (lo que envía Flask)

**URL:** `{contabilidad_base_url}/asientos/crear`  
**Método:** `POST`  
**Auth:** HTTP Basic  
**Content-Type:** `application/json`

### Entrada

```json
{
  "usuario": "nandos",
  "numLineasIn": 2,
  "lineas": [
    {
      "cuenta": "4000000186",
      "fecha": "20260630",
      "importe": 1000.0,
      "debe_haber": "D",
      "concepto": "Pago proveedor"
    },
    {
      "cuenta": "5720000001",
      "fecha": "20260630",
      "importe": 1000.0,
      "debe_haber": "H",
      "concepto": "Pago proveedor"
    }
  ]
}
```

### Salida esperada por Flask

```json
{
  "salida": {
    "success": true,
    "numero_asiento": 78432,
    "mensaje": "Asiento creado correctamente"
  }
}
```

En error: `success: false` y `mensaje` con el texto (Flask lo muestra al usuario).

---

## Arquitectura en el AS/400

```
POST JSON
   │
   ▼
Integrated Web Services (IAERP)
   │  deserializa JSON → DS tEntrada
   ▼
IAERPCAS (Main)          ← docs/iaerp_post_crear_asiento.rpgle
   │  valida + fecha cabecera
   ▼
CTB420 (NOMAIN export)   ← tu módulo con CTBCO / CTBSD / CTBSC
   │
   ▼
Ficheros contables
```

---

## Paso 1 — Compilar `CTB420` (módulo NOMAIN)

Tu fuente con `CTL-OPT NOMAIN` y `dcl-proc CTB420 export`.

```cl
CRTSRVPGM SRVPGM(MIALIB/CTB420SRV) MODULE(MIALIB/CTB420)
```

Ajusta librería/nombres. El procedimiento exportado debe llamarse exactamente `CTB420`.

---

## Paso 2 — Compilar el programa del POST

Fuente: `docs/iaerp_post_crear_asiento.rpgle`

1. Cambia en el prototipo:
   ```rpgle
   extpgm('MIALIB/CTB420SRV')
   ```
   por tu `SRVPGM` real.

2. Compila y crea el programa publicable:

```cl
CRTBNDRPG PGM(MIALIB/IAERPCAS) MODULE(MIALIB/IAERPCAS) +
            BNDSRVPGM((MIALIB/CTB420SRV))
```

`IAERPCAS` = nombre sugerido del handler REST (puedes usar otro).

**Importante:** el `dcl-pi` de `Main` tiene dos parámetros:

| Parámetro | DS | Origen |
|-----------|-----|--------|
| `entrada` | `tEntrada` | Body JSON |
| `respuesta` | `tRespuesta` | JSON de respuesta |

IWS debe mapear la **raíz del body** a `entrada` y devolver `respuesta` como JSON.

---

## Paso 3 — Publicar en Integrated Web Services Server

Entorno habitual (como PEDIDOS / IAERP en `:10014/web/services/IAERP`):

### 3.1 Desde ACS (IBM i Access Client Solutions)

1. **Configuration and Service** → **Web Services** → **Integrated Web Services Server**.
2. Selecciona el servidor existente **IAERP** (o crea uno nuevo en el puerto 10014).
3. **Deploy new service** / **Add ILE service program or program**.
4. Tipo: **ILE program** → `MIALIB/IAERPCAS`.
5. El asistente genera el descriptor (WSDL / OpenAPI según versión).

### 3.2 Definir la operación REST POST

Crea una operación con estas características:

| Propiedad | Valor |
|-----------|--------|
| Nombre operación | `crearAsiento` (interno) |
| URL path | `/asientos/crear` |
| Método HTTP | `POST` |
| Request body | JSON → estructura `entrada` |
| Response | JSON ← estructura `respuesta` |

### 3.3 Mapeo de campos JSON ↔ RPG

El body debe coincidir con `tEntrada`:

| JSON | Campo RPG | Tipo |
|------|-----------|------|
| `usuario` | `entrada.usuario` | string 20 |
| `numLineasIn` | `entrada.numLineasIn` | int |
| `lineas` | `entrada.lineas` | array |
| `lineas[].cuenta` | `cuenta` | string 10 |
| `lineas[].fecha` | `fecha` | string 8 |
| `lineas[].importe` | `importe` | decimal 15,2 |
| `lineas[].debe_haber` | `debe_haber` | string 1 |
| `lineas[].concepto` | `concepto` | string 50 |

**Array `lineas`:** en el descriptor IWS, el **Count** del array debe ser `numLineasIn` (igual que en pedidos con `numLineasIn` + `lineas`). No uses un máximo fijo 200 en el Count si el runtime lo rellena entero; si no puedes usar Count dinámico, limita `MAX_LINEAS` en RPG y en el wizard.

Respuesta:

| JSON | Campo RPG |
|------|-----------|
| `salida.success` | `respuesta.salida.success` (boolean) |
| `salida.numero_asiento` | `respuesta.salida.numero_asiento` |
| `salida.mensaje` | `respuesta.salida.mensaje` |

### 3.4 Autenticación

La app Flask envía Basic Auth (`AS400_API_USER` / `AS400_API_PASSWORD`). Configura el mismo usuario en el servidor IWS o en el proxy delante del AS/400.

### 3.5 Probar sin Flask

```bash
curl -s -u usuario:password \
  -H "Content-Type: application/json" \
  -d '{
    "usuario": "test",
    "numLineasIn": 2,
    "lineas": [
      {"cuenta":"4000000186","fecha":"20260630","importe":100,"debe_haber":"D","concepto":"Test D"},
      {"cuenta":"5720000001","fecha":"20260630","importe":100,"debe_haber":"H","concepto":"Test H"}
    ]
  }' \
  "http://TU_AS400:10014/web/services/IAERP/asientos/crear"
```

Respuesta OK:

```json
{"salida":{"success":true,"numero_asiento":12345,"mensaje":"Asiento creado correctamente"}}
```

---

## Paso 4 — Configurar Flask (`empresas.json`)

```json
{
  "contabilidad_base_url": "http://TU_AS400:10014/web/services/IAERP",
  "endpoints": {
    "cuentas": "/cuentas",
    "crear_asiento": "/asientos/crear"
  }
}
```

La app ya llama a `POST crear_asiento` con el JSON de arriba (`as400_api.py` → `crear_asiento_contable`).

---

## Paso 5 — Si el asistente IWS no mapea bien el JSON

Alternativa: programa único que parsea el body con **YAJL** y construye la respuesta a mano. Útil si la versión de IWS no soporta arrays con Count = `numLineasIn`.

Flujo:

1. Programa `IAERPCAS` recibe `char(65535)` o puntero al body.
2. `yajl_buf_load` + `yajl_get_*` para leer campos.
3. Rellenas `tEntrada` y llamas `CTB420`.
4. Montas JSON de salida con `yajl_gen_*` o plantilla fija.

En la mayoría de instalaciones con PEDIDOS ya funcionando, el mapeo directo DS ↔ JSON (paso 3) es suficiente: **copia la misma configuración que `/pedidos/crear`** cambiando solo estructuras y path.

---

## Checklist CTB420 (tu módulo)

Antes de enlazar al POST, revisa en `CTB420`:

- [ ] Fecha: `%date(fechaAsiento:*ymd)` o `%dec(%subst(...))`, no `*iso` sobre `20260630`
- [ ] Si no hay registro en `CTBCO`, crear o devolver error (no dejar `numeroAsiento = 0` sin mensaje claro)
- [ ] No omitir líneas con `codigoCuenta <= 0`; devolver `*off` con mensaje
- [ ] Validar cuadre debe/haber (la app ya lo hace, pero conviene en RPG)
- [ ] `STRCMTCTL` + `COMMIT`/`ROLBK` si quieres atomicidad entre `CTBSD` y `CTBSC`

---

## Resumen de nombres sugeridos

| Artefacto | Nombre sugerido |
|-----------|-----------------|
| Módulo grabación | `CTB420` (NOMAIN) en `CTB420SRV` |
| Programa REST POST | `IAERPCAS` |
| Path público | `/asientos/crear` |
| Servidor IWS | `IAERP` (existente) |
