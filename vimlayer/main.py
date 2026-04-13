"""VimLayer - Cross-platform Spotlight-like UI element navigation."""

import logging
import signal
import sys
from vimlayer.platforms import get_platform

def main():
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=logging.DEBUG,
    )

    platform = get_platform()
    
    # Platform-specific run loop
    try:
        platform.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.getLogger(__name__).exception("Application crashed: %s", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
