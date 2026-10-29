// -*- mode: js; js-indent-level: 4; indent-tabs-mode: nil -*-
// Xclipy's helper: what only Cinnamon can do for the clipboard history on
// Wayland. The interface is described in xclipy/helper.py.

const Clutter = imports.gi.Clutter;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const Meta = imports.gi.Meta;
const Main = imports.ui.main;

const XCLIPY_NAME = 'org.x.Xclipy';
const HELPER_NAME = 'org.x.Xclipy.Cinnamon';
const HELPER_PATH = '/org/x/Xclipy/Cinnamon';
const VERSION = 1;
// Xclipy's overlay: its application id and (untranslated) title.
const OVERLAY_APP_ID = 'org.x.Xclipy';
const OVERLAY_TITLE = 'Xclipy';
// Where the overlay goes, as Xclipy places it on X11 (xclipy/placement.py).
const GAP = 1;
const MARGIN = 12;
const HOLD_MS = 500;

const HelperIface =
    '<node> \
        <interface name="org.x.Xclipy.Cinnamon"> \
            <signal name="ClipboardChanged"> \
                <arg type="as" name="mimetypes" /> \
            </signal> \
            <method name="ReadClipboard"> \
                <arg type="s" direction="in" name="mimetype" /> \
                <arg type="ay" direction="out" name="data" /> \
            </method> \
            <method name="FocusedWindow"> \
                <arg type="s" direction="out" name="wm_class" /> \
                <arg type="s" direction="out" name="app_id" /> \
                <arg type="u" direction="out" name="pid" /> \
                <arg type="(iiii)" direction="out" name="origin" /> \
            </method> \
            <method name="PlaceOverlay"> \
                <arg type="(iiii)" direction="in" name="anchor" /> \
            </method> \
            <method name="Paste"> \
                <arg type="b" direction="in" name="terminal" /> \
            </method> \
            <property name="Version" type="u" access="read" /> \
        </interface> \
    </node>';

class XclipyHelper {
    constructor() {
        this._dbusImpl = Gio.DBusExportedObject.wrapJSObject(HelperIface, this);
        this._dbusImpl.export(Gio.DBus.session, HELPER_PATH);
        this._nameId = Gio.bus_own_name_on_connection(Gio.DBus.session, HELPER_NAME,
                                                      Gio.BusNameOwnerFlags.REPLACE, null, null);

        this._selection = global.display.get_selection();
        this._ownerChangedId = this._selection.connect('owner-changed', (selection, type, source) => {
            if (type !== Meta.SelectionType.SELECTION_CLIPBOARD || !source)
                return;
            this._dbusImpl.emit_signal('ClipboardChanged', new GLib.Variant('(as)', [source.get_mimetypes()]));
        });

        // The overlay isn't a window of its own for the window list or Alt+Tab.
        this._isInteresting = Main.isInteresting;
        Main.isInteresting = metaWindow => !this._isOverlay(metaWindow) && this._isInteresting(metaWindow);
        this._windowCreatedId = global.display.connect('window-created', (display, metaWindow) => {
            if (this._isOverlay(metaWindow))
                metaWindow.make_above();
        });
    }

    destroy() {
        Main.isInteresting = this._isInteresting;
        global.display.disconnect(this._windowCreatedId);
        this._selection.disconnect(this._ownerChangedId);
        Gio.bus_unown_name(this._nameId);
        this._dbusImpl.unexport();
        this._keyboard = null;
    }

    _isOverlay(metaWindow) {
        return metaWindow.get_gtk_application_id() === OVERLAY_APP_ID
            && metaWindow.get_title() === OVERLAY_TITLE;
    }

    get Version() {
        return VERSION;
    }

    // Some methods are only for Xclipy: the clipboard, the focused window and
    // pressing keys aren't for any application on the bus.
    _fromXclipy(invocation) {
        try {
            let owner = Gio.DBus.session.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                                   'org.freedesktop.DBus', 'GetNameOwner',
                                                   new GLib.Variant('(s)', [XCLIPY_NAME]),
                                                   new GLib.VariantType('(s)'),
                                                   Gio.DBusCallFlags.NONE, 500, null);
            if (owner.deep_unpack()[0] === invocation.get_sender())
                return true;
        } catch (e) {
            // Xclipy isn't running.
        }
        invocation.return_dbus_error('org.x.Xclipy.Cinnamon.Error.Denied', 'Only Xclipy may ask for this');
        return false;
    }

    ReadClipboardAsync(params, invocation) {
        if (!this._fromXclipy(invocation))
            return;
        let [mimetype] = params;
        let stream = Gio.MemoryOutputStream.new_resizable();
        this._selection.transfer_async(Meta.SelectionType.SELECTION_CLIPBOARD, mimetype, -1, stream, null,
                                       (selection, result) => {
            let data = [];
            try {
                selection.transfer_finish(result);
                stream.close(null);
                data = stream.steal_as_bytes().toArray();
            } catch (e) {
                // Nothing of that kind on the clipboard.
            }
            invocation.return_value(new GLib.Variant('(ay)', [data]));
        });
    }

    FocusedWindowAsync(params, invocation) {
        if (!this._fromXclipy(invocation))
            return;
        let metaWindow = global.display.focus_window;
        let result = ['', '', 0, [0, 0, 0, 0]];
        if (metaWindow && !this._isOverlay(metaWindow)) {
            // Where the application's own window coordinates start: its whole
            // surface (shadows too) if it draws its decorations, else inside ours.
            let rect = metaWindow.get_client_type() === Meta.WindowClientType.WAYLAND || metaWindow.is_client_decorated()
                ? metaWindow.get_buffer_rect()
                : metaWindow.frame_rect_to_client_rect(metaWindow.get_frame_rect());
            result = [metaWindow.get_wm_class() || '', metaWindow.get_gtk_application_id() || '',
                      Math.max(0, metaWindow.get_pid()), [rect.x, rect.y, rect.width, rect.height]];
        }
        invocation.return_value(new GLib.Variant('(ssu(iiii))', result));
    }

    // The anchor is unused: the overlay opens at the mouse pointer, which only
    // Cinnamon knows on Wayland.
    PlaceOverlayAsync(params, invocation) {
        invocation.return_value(null);
        // Right after Xclipy shows it the overlay may not be mapped yet: it
        // has no size until then, and the window manager places it itself.
        let tries = 20;
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 25, () => {
            let metaWindow = global.get_window_actors().map(actor => actor.get_meta_window())
                                                       .find(w => this._isOverlay(w) && w.get_frame_rect().width > 0);
            if (metaWindow) {
                this._place(metaWindow);
                return GLib.SOURCE_REMOVE;
            }
            return --tries > 0 ? GLib.SOURCE_CONTINUE : GLib.SOURCE_REMOVE;
        });
    }

    // At the bottom right of the mouse pointer, to its left or above it near the
    // edges; in the bottom right corner only without a pointer (xclipy/placement.py).
    _place(metaWindow) {
        let [pointerX, pointerY] = global.get_pointer();
        let pointer = pointerX >= 0 && pointerY >= 0;
        let monitor = pointer ? global.display.get_monitor_index_for_rect(new Meta.Rectangle({x: pointerX, y: pointerY, width: 1, height: 1}))
                              : global.display.get_current_monitor();
        let area = global.workspace_manager.get_active_workspace().get_work_area_for_monitor(monitor);
        let frame = metaWindow.get_frame_rect();
        let right = area.x + area.width, bottom = area.y + area.height;
        let x, y;
        if (!pointer) {
            x = right - frame.width - MARGIN;
            y = bottom - frame.height - MARGIN;
        } else {
            x = pointerX + GAP;
            if (x + frame.width > right && pointerX - GAP - frame.width >= area.x)
                x = pointerX - GAP - frame.width;
            y = pointerY + GAP;
            if (y + frame.height > bottom && pointerY - GAP - frame.height >= area.y)
                y = pointerY - GAP - frame.height;
            x = Math.min(Math.max(x, area.x), right - frame.width);
            y = Math.min(Math.max(y, area.y), bottom - frame.height);
        }
        this._moveAndHold(metaWindow, x, y);
        metaWindow.make_above();
        metaWindow.stick();
        metaWindow.activate(global.get_current_time());
    }

    // On Wayland the window manager can still apply where it first put the
    // overlay when the application acknowledges that late, after the move:
    // keep the overlay where it belongs for a moment.
    _moveAndHold(metaWindow, x, y) {
        metaWindow.move_frame(true, x, y);
        let held = metaWindow.connect('position-changed', w => {
            let frame = w.get_frame_rect();
            if (frame.x !== x || frame.y !== y)
                w.move_frame(true, x, y);
        });
        let unmanaged = metaWindow.connect('unmanaged', () => release());
        // Being dragged: the new place is the user's.
        let grabbed = global.display.connect('grab-op-begin', (display, window) => {
            if (window === metaWindow)
                release();
        });
        let release = () => {
            if (held) {
                metaWindow.disconnect(held);
                metaWindow.disconnect(unmanaged);
                global.display.disconnect(grabbed);
                held = 0;
            }
            return GLib.SOURCE_REMOVE;
        };
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, HOLD_MS, release);
    }

    PasteAsync(params, invocation) {
        if (!this._fromXclipy(invocation))
            return;
        let [terminal] = params;
        invocation.return_value(null);
        if (!this._keyboard) {
            let seat = Clutter.get_default_backend().get_default_seat();
            this._keyboard = seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        }
        let keys = terminal ? [Clutter.KEY_Control_L, Clutter.KEY_Shift_L, Clutter.KEY_v]
                            : [Clutter.KEY_Control_L, Clutter.KEY_v];
        let time = GLib.get_monotonic_time();
        for (let key of keys)
            this._keyboard.notify_keyval(time, key, Clutter.KeyState.PRESSED);
        for (let key of keys.reverse())
            this._keyboard.notify_keyval(time, key, Clutter.KeyState.RELEASED);
    }
}

let helper = null;

function init(metadata) {
}

function enable() {
    helper = new XclipyHelper();
}

function disable() {
    if (helper) {
        helper.destroy();
        helper = null;
    }
}
