# Changelog

## 0.1.2 - 2026-08-17

- Versión coherente entre el paquete Python, la app Frappe y el agente HTTP.
- Pruebas nativas de cola multiempresa, idempotencia, recepción, reintento,
  reconciliación de cancelaciones y limpieza de campos al desinstalar.
- El script nativo desinstala el nombre de distribución correcto.
- La cola usa el parámetro de límite vigente en Frappe 16.

## 0.1.1 - 2026-08-17

- El nombre de distribución coincide con el nombre técnico Frappe
  `govp_erpnext`, de modo que `bench get-app` y las imágenes por capas no
  renombran la app a un módulo inexistente.
- Prueba de regresión para el contrato entre el paquete Python y Frappe.

## 0.1.0 - 2026-08-17

- App Frappe abierta para ERPNext 15/16.
- Emisión en Delivery Note y comprobación en Purchase Receipt.
- Lotes, series, multiempresa, idempotencia y reintentos en cola.
- Campos y ajustes sin código, secreto Password y guardas SSRF.
- Banco unitario autocontenido y puerta de aceptación nativa reproducible.
