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
const VERSION = 2;
// Xclipy's overlays: their application id and (untranslated) title.
const OVERLAY_APP_ID = 'org.x.Xclipy';
const OVERLAY_TITLE = 'Xclipy';
// Where an overlay goes, by the rule of xclipy/placement.py.
const GAP = 1;
const MARGIN = 12;
// An overlay opens right after Xclipy asked where it goes; a position asked
// for longer ago than this is stale.
const PENDING_US = 2 * GLib.USEC_PER_SEC;
// How long an opening overlay waits, unseen, for the application to take its
// position (at most; usually one frame).
const SETTLE_MS = 60;

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
            </method> \
            <method name="PrepareOverlay"> \
                <arg type="(ii)" direction="in" name="size" /> \
                <arg type="i" direction="out" name="x" /> \
                <arg type="i" direction="out" name="y" /> \
                <arg type="s" direction="out" name="side" /> \
            </method> \
            <method name="Paste"> \
                <arg type="b" direction="in" name="terminal" /> \
            </method> \
            <property name="Version" type="u" access="read" /> \
        </interface> \
    </node>';

// The top left corner of an overlay of size [width, height] and its side, at the
// mouse pointer [x, y] (or null: the bottom right corner) in the work area.
function place(size, area, pointer) {
    let [width, height] = size;
    let right = area.x + area.width, bottom = area.y + area.height;
    if (!pointer)
        return [right - width - MARGIN, bottom - height - MARGIN, 'bottom-right'];
    let [pointerX, pointerY] = pointer;
    let vertical = 'bottom', horizontal = 'right';
    let x = pointerX + GAP;
    if (x + width > right && pointerX - GAP - width >= area.x) {
        x = pointerX - GAP - width;
        horizontal = 'left';
    }
    let y = pointerY + GAP;
    if (y + height > bottom && pointerY - GAP - height >= area.y) {
        y = pointerY - GAP - height;
        vertical = 'top';
    }
    x = Math.min(Math.max(x, area.x), right - width);
    y = Math.min(Math.max(y, area.y), bottom - height);
    return [x, y, vertical + '-' + horizontal];
}

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

        // The overlays aren't windows of their own for the window list or Alt+Tab.
        this._isInteresting = Main.isInteresting;
        Main.isInteresting = metaWindow => !this._isOverlay(metaWindow) && this._isInteresting(metaWindow);
        // Where the overlay opening next goes: {x, y, until}.
        this._pending = null;
        this._windowCreatedId = global.display.connect('window-created', (display, metaWindow) => {
            this._whenIdentified(metaWindow);
        });
        this._mapId = global.window_manager.connect('map', (wm, actor) => this._onMap(actor));
        // Overlays can't be moved or resized.
        this._grabId = global.display.connect('grab-op-begin', (display, object, metaWindow, op) => {
            // Ended right after it began, outside the signal that announces it.
            if (metaWindow && this._isOverlay(metaWindow))
                GLib.idle_add(GLib.PRIORITY_HIGH, () => {
                    if (display.get_grab_op() !== Meta.GrabOp.NONE)
                        display.end_grab_op(global.get_current_time());
                    return GLib.SOURCE_REMOVE;
                });
        });
    }

    destroy() {
        Main.isInteresting = this._isInteresting;
        global.display.disconnect(this._grabId);
        global.window_manager.disconnect(this._mapId);
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

    // A new window only says what it is a moment later, on Wayland, but
    // before it is shown.
    _whenIdentified(metaWindow) {
        let ids = [];
        let forget = () => {
            ids.forEach(id => metaWindow.disconnect(id));
            ids = [];
        };
        let check = () => {
            if (!this._isOverlay(metaWindow))
                return;
            forget();
            metaWindow.make_above();
            metaWindow.stick();
            let pending = this._pending;
            this._pending = null;
            if (pending && GLib.get_monotonic_time() < pending.until)
                metaWindow._xclipyPosition = [pending.x, pending.y];
        };
        ids = ['notify::title', 'notify::gtk-application-id'].map(signal => metaWindow.connect(signal, check));
        ids.push(metaWindow.connect('unmanaged', forget));
        check();
    }

    // Step two, on Wayland: Cinnamon places a new window itself as it shows it,
    // where it sees fit, and no application can choose. So the overlay opens
    // unseen, goes where step one said, and only then appears: it never moves
    // on the screen. (The application takes its position at its next frame,
    // until then Cinnamon may put it back where it first placed it.) On X11
    // Xclipy opens it there itself.
    _onMap(actor) {
        let metaWindow = actor.meta_window;
        let position = metaWindow._xclipyPosition;
        if (!position || metaWindow.get_client_type() !== Meta.WindowClientType.WAYLAND)
            return;
        delete metaWindow._xclipyPosition;
        let [x, y] = position;
        actor.remove_all_transitions();  // Cinnamon's opening animation starts from where it placed it
        actor.opacity = 0;
        let movedBack = false;
        let settled = 0, timeout = 0;
        let reveal = () => {
            if (settled) {
                metaWindow.disconnect(settled);
                settled = 0;
                GLib.source_remove(timeout);
                actor.opacity = 255;
            }
            return GLib.SOURCE_REMOVE;
        };
        let atPosition = () => {
            let frame = metaWindow.get_frame_rect();
            return frame.x === x && frame.y === y;
        };
        settled = metaWindow.connect('position-changed', () => {
            if (!atPosition()) {
                movedBack = true;
                metaWindow.move_frame(false, x, y);
            } else if (movedBack) {
                reveal();
            }
        });
        timeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, SETTLE_MS, reveal);
        metaWindow.connect('unmanaged', reveal);
        metaWindow.move_frame(false, x, y);
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
        let result = ['', '', 0];
        if (metaWindow && !this._isOverlay(metaWindow))
            result = [metaWindow.get_wm_class() || '', metaWindow.get_gtk_application_id() || '',
                      Math.max(0, metaWindow.get_pid())];
        invocation.return_value(new GLib.Variant('(ssu)', result));
    }

    // Step one of opening an overlay: where it goes, at the mouse pointer (which
    // only Cinnamon knows on Wayland), and on which side of it.
    PrepareOverlayAsync(params, invocation) {
        if (!this._fromXclipy(invocation))
            return;
        let [size] = params;
        let [pointerX, pointerY] = global.get_pointer();
        let pointer = pointerX >= 0 && pointerY >= 0 ? [pointerX, pointerY] : null;
        let monitor = pointer
            ? global.display.get_monitor_index_for_rect(new Meta.Rectangle({x: pointerX, y: pointerY, width: 1, height: 1}))
            : global.display.get_current_monitor();
        let area = global.workspace_manager.get_active_workspace().get_work_area_for_monitor(monitor);
        let [x, y, side] = place(size, area, pointer);
        this._pending = {x: x, y: y, until: GLib.get_monotonic_time() + PENDING_US};
        invocation.return_value(new GLib.Variant('(iis)', [x, y, side]));
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
