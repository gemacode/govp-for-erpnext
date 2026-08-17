# Validación nativa de GOVP for ERPNext 0.1.3

Fecha: 2026-08-17  
Revisión publicada: `fc6c17d91ae0f14546cfc073af89e956055c9274`

## Resultado

La puerta técnica nativa está superada para ERPNext 15 y 16. En ambas ramas se
comprobó la instalación de `govp_erpnext`, la migración, el acceso HTTP, la carga
del módulo en backend, worker y scheduler, y el ciclo funcional de emisión y
verificación.

| Entorno | Base verificada | Resultado |
| --- | --- | --- |
| ERPNext 15 | ERPNext 15.119.2, Frappe 15.118.0, MariaDB 10.6; imagen ERPNext `sha256:c6583cc6b945460f608283af7c825eb881e4d9a7eedfb6f27aa7ee0434713c5e`; MariaDB `sha256:2fdc84794931c0abde9ba6a8c9cb5a4635a02d851a103f0301a8b606dfc5cd98` | HTTP 200, app 0.1.3, 10/10 pruebas nativas |
| ERPNext 16 | ERPNext 16.32.1, Frappe 16.31.0, MariaDB 11.8; imagen ERPNext `sha256:c60e59639d94a21669a986b4a312191c9f58dbd0f6ae5b1f4f426c00eb7e4839` | HTTP 200, app 0.1.3, 10/10 pruebas nativas |

Además, las 19 pruebas autocontenidas del núcleo y del contrato de paquete pasan
en CI. La ejecución nativa cubre:

- creación y envío de una Delivery Note real;
- creación y envío de una Purchase Receipt real;
- emisión, verificación, reintento acotado e idempotencia;
- aislamiento entre compañías;
- reclamación atómica para impedir que dos workers procesen el mismo job;
- reconciliación humana tras cancelación;
- desinstalación que elimina únicamente los campos propiedad del conector y
  reinstalación posterior;
- importación de la versión 0.1.3 desde worker y scheduler.

## Puertas que no cubre esta evidencia

La validación no sustituye un piloto contra una cuenta externa de GOVP Exchange
ni el uso supervisado con documentos de una empresa real. Esas dos puertas, y
la evaluación de una instalación guiada sin terminal, permanecen abiertas antes
de declarar el conector apto para producción general.
