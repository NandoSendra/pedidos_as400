      //****************************************************************
      // Fragmento para integrar en tu módulo NOMAIN (mismo SRVPGM que
      // getArticulos / crearPedido). Sustituye tu dcl-proc crearAsiento.
      //
      // En IWS: operación POST /asientos/crear, igual que crearPedido:
      //   Entrada: usuario, numLineasIn, lineas[]
      //   Salida:  salida { success, numero_asiento, mensaje }
      //****************************************************************

      // --- Poner ANTES de tLineaAsiento / tEntradaAsiento (nivel módulo) ---
      dcl-c MAX_LINEAS_ASIENTO 200;
      dcl-c LEN_CUENTA           10;
      dcl-c LEN_FECHA             8;
      dcl-c LEN_DH                1;
      dcl-c LEN_CONCEPTO         50;
      dcl-c LEN_USUARIO          20;

      // Si validas cuenta aquí, declara el fichero del plan (ajusta nombre):
      // dcl-f ctbmcla usage(*input) keyed;

      // --- DS (nivel módulo; reemplaza las que usan LEN_* sin definir) ---
      dcl-ds tLineaAsiento qualified template;
        cuenta     char(LEN_CUENTA);
        fecha      char(LEN_FECHA);
        importe    packed(15:2);
        debe_haber char(LEN_DH);
        concepto   char(LEN_CONCEPTO);
      end-ds;

      dcl-ds tSalidaAsiento qualified template;
        success        ind;
        numero_asiento packed(6:0);
        mensaje        char(256);
      end-ds;

      // CTB420 en el mismo SRVPGM (sin extpgm) o en otro:
      // dcl-pr CTB420 ind extproc('CTB420') extpgm('MIALIB/CTB420SRV');
      dcl-pr CTB420 ind extproc('CTB420');
        usuario       char(LEN_USUARIO) const;
        numLineas     int(10) const;
        fechaAsiento  packed(8:0) const;
        lineas        likeds(tLineaAsiento) dim(MAX_LINEAS_ASIENTO) const;
        numeroAsiento packed(6:0);
        mensajeError  char(256);
      end-pr;


      dcl-proc crearAsiento export;

        // Mismo estilo que crearPedido: parámetros planos = raíz del JSON
        dcl-pi *n;
          usuario     char(LEN_USUARIO) const;
          numLineasIn int(10) const;
          lineas      likeds(tLineaAsiento) dim(MAX_LINEAS_ASIENTO) const;
          salida      likeds(tSalidaAsiento);
        end-pi;

        dcl-s i            int(10);
        dcl-s totalDebe    packed(15:2);
        dcl-s totalHaber   packed(15:2);
        dcl-s dif          packed(15:2);
        dcl-s fechaAsiento packed(8:0);
        dcl-s codigoCuenta packed(10:0);
        dcl-s mensajeError char(256);
        dcl-s usuarioCTB   char(LEN_USUARIO);

        clear salida;
        salida.success = *off;
        salida.numero_asiento = 0;
        salida.mensaje = '';

        if numLineasIn < 2
           or numLineasIn > MAX_LINEAS_ASIENTO;
          salida.mensaje = 'El asiento debe tener entre 2 y '
                         + %char(MAX_LINEAS_ASIENTO) + ' lineas';
          return;
        endif;

        totalDebe = 0;
        totalHaber = 0;

        for i = 1 to numLineasIn;

          if %trim(lineas(i).cuenta) = '';
            salida.mensaje = 'Linea ' + %char(i) + ': falta cuenta';
            return;
          endif;

          if %len(%trim(lineas(i).fecha)) <> LEN_FECHA
             or %check('0123456789': lineas(i).fecha) > 0;
            salida.mensaje = 'Linea ' + %char(i) + ': fecha no valida';
            return;
          endif;

          if lineas(i).importe <= 0;
            salida.mensaje = 'Linea ' + %char(i) + ': importe debe ser > 0';
            return;
          endif;

          if lineas(i).debe_haber <> 'D'
             and lineas(i).debe_haber <> 'H';
            salida.mensaje = 'Linea ' + %char(i) + ': debe_haber debe ser D o H';
            return;
          endif;

          if %trim(lineas(i).concepto) = '';
            salida.mensaje = 'Linea ' + %char(i) + ': falta concepto';
            return;
          endif;

          monitor;
            codigoCuenta = %dec(lineas(i).cuenta: LEN_CUENTA: 0);
          on-error;
            salida.mensaje = 'Linea ' + %char(i) + ': cuenta no numerica';
            return;
          endmon;

          // Validación plan de cuentas (ajusta CHAIN a tu fichero/clave)
          chain (3:codigoCuenta) rgctbmc;
          if not %found(ctbmcla);
            salida.mensaje = 'Linea ' + %char(i)
                           + ': cuenta no existe en el plan';
            return;
          endif;

          if lineas(i).debe_haber = 'D';
            totalDebe += lineas(i).importe;
          else;
            totalHaber += lineas(i).importe;
          endif;

        endfor;

        dif = totalDebe - totalHaber;
        if %abs(dif) >= 0.01;
          salida.mensaje = 'Asiento descuadrado: debe '
                         + %char(totalDebe) + ' haber ' + %char(totalHaber);
          return;
        endif;

        monitor;
          fechaAsiento = %dec(lineas(1).fecha: LEN_FECHA: 0);
        on-error;
          salida.mensaje = 'Fecha de la linea 1 no numerica';
          return;
        endmon;

        usuarioCTB = %trim(usuario);

        if CTB420( usuarioCTB
                 : numLineasIn
                 : fechaAsiento
                 : lineas
                 : salida.numero_asiento
                 : mensajeError );
          salida.success = *on;
          salida.mensaje = 'Asiento creado correctamente';
        else;
          salida.mensaje = mensajeError;
        endif;

        return;

      end-proc;
