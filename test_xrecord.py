import sys
from Xlib import display, X
from Xlib.ext import record
from Xlib.protocol import rq

def main():
    disp = display.Display()
    if not disp.has_extension('RECORD'):
        print("Error: RECORD extension not found on this X server.")
        sys.exit(1)

    print("RECORD extension found. Starting global listener...")
    print("Press keys (Ctrl+C to stop)...")

    ctx = disp.record_create_context(
        0,
        [record.AllClients],
        [{
            'core_requests': (0, 0),
            'core_replies': (0, 0),
            'ext_requests': (0, 0, 0, 0),
            'ext_replies': (0, 0, 0, 0),
            'delivered_events': (0, 0),
            'device_events': (X.KeyPress, X.KeyRelease),
            'errors': (0, 0),
            'client_started': False,
            'client_died': False,
        }]
    )

    def handler(reply):
        if reply.category != record.FromServer: return
        if reply.client_swapped: return
        
        data = reply.data
        while len(data):
            event, data = rq.EventField(None).parse_binary_value(data, disp.display, None, None)
            if event.type == X.KeyPress:
                print(f"Key pressed: scancode={event.detail}")
            elif event.type == X.KeyRelease:
                pass

    try:
        disp.record_enable_context(ctx, handler)
    except KeyboardInterrupt:
        pass
    finally:
        disp.record_free_context(ctx)

if __name__ == "__main__":
    main()
