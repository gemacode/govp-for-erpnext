frappe.ui.form.on("GOVP Company Settings", {
  refresh(frm) {
    if (!frm.is_new()) {
      const label = frm.doc.enabled ? __("Comprobar conexión") : __("Comprobar y activar");
      frm.add_custom_button(label, async () => {
        if (frm.is_dirty()) await frm.save();
        const result = await frappe.call({
          method: "govp_erpnext.api.test_connection",
          args: { company: frm.doc.company },
          freeze: true,
          freeze_message: __("Comprobando GOVP Exchange…"),
        });
        if (result.message?.ok) {
          if (!frm.doc.enabled) {
            await frm.set_value("enabled", 1);
            await frm.save();
          }
          frappe.show_alert({ message: __("Conexión GOVP correcta y compañía activada"), indicator: "green" });
        }
      });
    }
  },
});
