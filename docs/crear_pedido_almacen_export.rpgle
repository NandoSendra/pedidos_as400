      //****************************************************************
      // Fragmento para integrar almacén en crearPedido (mismo SRVPGM
      // que getArticulos / getProveedores / crearAsiento).
      //
      // Contrato JSON Flask (POST /pedidos/crear):
      //   {
      //     "cliente": 4000000001,
      //     "usuario": "nombre_usuario",
      //     "almacen": 1,
      //     "numLineasIn": 2,
      //     "lineas": [
      //       { "codigo_articulo": "...", "cantidad": 10, "codigoUm": 1 }
      //     ]
      //   }
      //
      // En empresas.json activar:
      //   "pedido_campo_almacen": "almacen"
      //
      // IMPORTANTE: ajusta la firma de PDP420 a la real de tu sistema.
      // El ejemplo añade pAlmacen justo después de pCliente.
      //****************************************************************

      // --- Sustituir tu dcl-pr PDP420 actual por esta versión ---
      dcl-pr PDP420 extpgm('PDP420');
        pCliente        packed(10:0);
        pAlmacen        packed(3:0);
        pUsuario        char(10);
        pNumLineas      int(10);
        pArticulos      char(13) dim(200);
        pCantidades     packed(11:3) dim(200);
        pCodigosUm      packed(2:0) dim(200);
        pNumeroPedido   packed(10:0);
        pCodRet         char(1);
        pMensaje        char(200);
      end-pr;


      // --- Sustituir tu dcl-proc crearPedido export actual ---
      dcl-proc crearPedido export;

        dcl-pi *n;
          cliente     packed(10:0) const;
          usuario     char(10);
          almacen     packed(3:0) const;
          numLineasIn int(10) const;
          lineas      likeds(LineaPedido) dim(200) const;
          salida      likeds(PedidoRespuesta);
        end-pi;

        dcl-s i              int(10);
        dcl-s codigoArticulo char(13);
        dcl-s cantidad       packed(11:3);
        dcl-s codigoUm       packed(2:0);

        dcl-s numLineas      int(10);
        dcl-s numeroPedido   packed(10:0) inz(0);

        dcl-s aArticulos     char(13) dim(9999);
        dcl-s aCantidades    packed(11:3) dim(9999);
        dcl-s acodigosUm     packed(2:0) dim(9999);

        dcl-s codRet         char(1);
        dcl-s mensajeRet     char(200);
        dcl-s clienteTrabajo packed(10:0);
        dcl-s almacenTrabajo packed(3:0);

        clear salida;
        clear aArticulos;
        clear aCantidades;
        clear acodigosUm;

        salida.success = *off;
        salida.numero_pedido = 0;
        salida.mensaje = '';

        if cliente <= 0;
          salida.mensaje = 'Cliente no valido';
          return;
        endif;

        if almacen <= 0;
          salida.mensaje = 'Almacen no valido';
          return;
        endif;

        chain almacen RGALMAL;
        if not %found(almalla);
          salida.mensaje = 'Almacen no existe: ' + %char(almacen);
          return;
        endif;

        numLineas = numLineasIn;

        if numLineas <= 0;
          salida.mensaje = 'Pedido sin lineas';
          return;
        endif;

        if numLineas > 9999;
          numLineas = 9999;
        endif;

        clienteTrabajo = cliente;
        almacenTrabajo = almacen;

        for i = 1 to numLineas;

          codigoArticulo = %trim(lineas(i).codigo_articulo);
          cantidad = lineas(i).cantidad;
          codigoUm = lineas(i).codigoUm;

          if codigoArticulo = *blank;
            salida.mensaje = 'Hay una linea sin articulo';
            return;
          endif;

          if cantidad <= 0;
            salida.mensaje = 'Hay una linea con cantidad no valida';
            return;
          endif;

          chain codigoArticulo RGALMAR;
          if not %found(ALMARLA);
            salida.mensaje = 'Articulo no existe: ' + %trim(codigoArticulo);
            return;
          endif;

          aArticulos(i) = codigoArticulo;
          aCantidades(i) = cantidad;
          acodigosUm(i) = codigoUm;

        endfor;

        clear numeroPedido;
        clear codRet;
        clear mensajeRet;

        PDP420(
          clienteTrabajo:
          almacenTrabajo:
          usuario:
          numLineas:
          aArticulos:
          aCantidades:
          acodigosUm:
          numeroPedido:
          codRet:
          mensajeRet
        );

        if codRet <> '0';
          salida.success = *off;
          salida.numero_pedido = 0;
          salida.mensaje = mensajeRet;
          return;
        endif;

        salida.success = *on;
        salida.numero_pedido = numeroPedido;
        salida.mensaje = mensajeRet;
        return;

      end-proc;
