i18n = import('i18n')
gnome = import('gnome')

install_data(
  'org.x.xclipy.gschema.xml',
  install_dir: datadir / 'glib-2.0' / 'schemas',
)
install_data(
  'xclipy.svg',
  install_dir: datadir / 'icons' / 'hicolor' / 'scalable' / 'apps',
)
# Themes don't have a filter icon.
install_data(
  'icons/xclipy-filter-symbolic.svg',
  install_dir: datadir / 'icons' / 'hicolor' / 'scalable' / 'actions',
)

# The overlay, and its page in System Settings.
foreach desktop_id : ['org.x.Xclipy', 'cinnamon-settings-xclipy']
  i18n.merge_file(
    input: desktop_id + '.desktop.in',
    output: desktop_id + '.desktop',
    type: 'desktop',
    po_dir: meson.project_source_root() / 'po',
    install: true,
    install_dir: datadir / 'applications',
  )
endforeach

gnome.post_install(
  glib_compile_schemas: true,
  gtk_update_icon_cache: true,
)
