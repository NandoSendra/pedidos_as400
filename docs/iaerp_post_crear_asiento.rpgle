      **free
      //****************************************************************
      // Programa publicado en IWS como POST /asientos/crear
      // Recibe JSON de pedidos_as400 (Flask) y llama a CTB420.
      //
      // JSON entrada (raíz del body):
      //   usuario, numLineasIn, lineas[]
      //
      // JSON salida:
      //   { "salida": { "success", "numero_asiento", "mensaje" } }
      //
      // Compilar módulo CTB420 (NOMAIN) en el mismo SRVPGM o enlazar
      // extpgm al service program donde está CTB420.
      //****************************************************************
      ctl-opt dftactgrp(*no) actgrp(*new) main(Main);

      dcl-c MAX_LINEAS   200;
      dcl-c LEN_CUENTA    10;
      dcl-c LEN_FECHA      8;
      dcl-c LEN_DH         1;
      dcl-c LEN_CONCEPTO  50;
      dcl-c LEN_USUARIO   20;

      // --- Misma DS de línea que CTB420 ---
      dcl-ds tLineaAsiento qualified template;
        cuenta     char(LEN_CUENTA);
        fecha      char(LEN_FECHA);
        importe    packed(15:2);
        debe_haber char(LEN_DH);
        concepto   char(LEN_CONCEPTO);
      end-ds;

      // --- Entrada REST (mapeo 1:1 con JSON body) ---
      dcl-ds tEntrada qualified;
        usuario     char(LEN_USUARIO);
        numLineasIn int(10);
        lineas      likeds(tLineaAsiento) dim(MAX_LINEAS);
      end-ds;

      // --- Salida anidada bajo "salida" (espera Flask) ---
      dcl-ds tSalida qualified template;
        success        ind;
        numero_asiento packed(6:0);
        mensaje        char(256);
      end-ds;

      dcl-ds tRespuesta qualified;
        salida likeds(tSalida);
      end-ds;

      // Prototipo de tu rutina de grabación (módulo NOMAIN CTB420)
      // Ajusta extpgm al SRVPGM real, p. ej. 'MIALIB/CTB420SRV'
      dcl-pr CTB420 ind extproc('CTB420') extpgm('MIALIB/CTB420SRV');
        usuario      char(LEN_USUARIO) const;
        numLineas    int(10)         const;
        fechaAsiento packed(8:0)      const;
        lineas       likeds(tLineaAsiento) dim(MAX_LINEAS) const;
        numeroAsiento packed(6:0);
        mensajeError char(256);
      end-pr;

      dcl-proc Main;
        dcl-pi *n;
          entrada   likeds(tEntrada);
          respuesta likeds(tRespuesta);
        end-pi;

        dcl-s fechaAsiento packed(8:0);
        dcl-s mensaje    char(256);

        clear respuesta;
        respuesta.salida.success = *off;
        respuesta.salida.numero_asiento = 0;
        respuesta.salida.mensaje = '';

        // --- Validaciones mínimas antes de CTB420 ---
        if entrada.numLineasIn < 2
           or entrada.numLineasIn > MAX_LINEAS;
          respuesta.salida.mensaje =
            'El asiento debe tener entre 2 y ' + %char(MAX_LINEAS) + ' lineas';
          return;
        endif;

        if %trim(entrada.lineas(1).fecha) = ''
           or %len(%trim(entrada.lineas(1).fecha)) <> LEN_FECHA;
          respuesta.salida.mensaje =
            'Falta fecha valida en la linea 1 (YYYYMMDD)';
          return;
        endif;

        monitor;
          fechaAsiento = %dec(entrada.lineas(1).fecha: LEN_FECHA: 0);
        on-error;
          respuesta.salida.mensaje =
            'Fecha de la linea 1 no numerica';
          return;
        endmon;

        // Fecha cabecera = primera línea (la app suele mandar la misma en todas)
        if CTB420( entrada.usuario
                 : entrada.numLineasIn
                 : fechaAsiento
                 : entrada.lineas
                 : respuesta.salida.numero_asiento
                 : mensaje );
          respuesta.salida.success = *on;
          respuesta.salida.mensaje = 'Asiento creado correctamente';
        else;
          respuesta.salida.mensaje = mensaje;
        endif;

        return;

      end-proc;
