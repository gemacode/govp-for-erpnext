frappe.ui.form.on("GOVP Company Settings", {
  refresh(frm) {
    if (!frm.is_new()) {
      frm.add_custom_button(__("Comprobar conexión"), async () => {
        const result = await frappe.call({
          method: "govp_erpnext.api.test_connection",
          args: { company: frm.doc.company },
          freeze: true,
          freeze_message: __("Comprobando GOVP Exchange…"),
        });
        if (result.message?.ok) frappe.show_alert({ message: __("Conexión GOVP correcta"), indicator: "green" });
      });
    }
  },
});
