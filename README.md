# GOVP for ERPNext

App abierta para Frappe/ERPNext que automatiza la relación de una pequeña
empresa con GOVP Exchange sin exigirle programar:

- emite un GOVP al enviar una **Delivery Note**;
- comprueba el GOVP indicado al recibir una **Purchase Receipt**;
- minimiza los datos y conserva una huella canónica de líneas, lotes y series;
- separa credenciales, idempotencia y cola por compañía;
- reintenta fallos transitorios sin duplicar GOVP.

## Estado 0.1.4

Candidato abierto. El núcleo y el contrato Frappe tienen 23 pruebas
autocontenidas. La instalación, migración, documentos completos y 11 pruebas
nativas están verificadas en ERPNext 15 y 16. La puerta técnica está superada;
siguen pendientes un piloto externo y uso supervisado en producción.

## Instalación

Desde el directorio de un bench que ya tenga ERPNext:

```bash
bench get-app https://github.com/gemacode/govp-for-erpnext
bench --site su-sitio install-app govp_erpnext
bench --site su-sitio migrate
```

Abra **GOVP Company Settings**: la app crea automáticamente una configuración
inactiva para cada compañía existente y para cada compañía que se añada después.
Pegue el token de conector y pulse **Comprobar y activar**. La compañía solo se
activa cuando Exchange responde correctamente. El token es un campo Password y
no se escribe en logs. La URL predeterminada es
`https://partners.gemacode.org/api/exchange` y se exige HTTPS.

En cada albarán aparecen campos de estado de solo lectura. En una recepción, el
usuario pega el código GOVP entregado por su proveedor; el conector lo comprueba
al confirmar el documento.

## Verificación

```bash
python3 -m unittest discover -s tests -v
bash tests/native-smoke.sh /ruta/a/frappe-bench sitio.local
```

La segunda orden instala la app en un sitio nativo existente, ejecuta sus tests y
desinstala únicamente la app. Nunca elimina el sitio ni la base de datos.

La matriz, las versiones y las puertas restantes están documentadas en
[NATIVE_VALIDATION.md](NATIVE_VALIDATION.md).

## Datos y seguridad

No se transmiten nombres, correo, dirección o teléfono del cliente/proveedor.
Exchange recibe compañía emisora, identificador del documento y una huella
SHA-256 de producto, cantidad, unidad, almacén, lote y serie. La URL se valida
contra HTTPS, credenciales embebidas y destinos privados para reducir SSRF.

Código y releases: <https://github.com/gemacode/govp-for-erpnext>.
