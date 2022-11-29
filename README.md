# LIFX Beta for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

**WARNING**: This is an unstable release. Do not install in a live or production
system.

This is a pre-release/testing version of the core LIFX integration. This repo
exists purely to make it easier to install the test version via HACS instead of
having to do it manually.

**WARNING**: if you prefer stability, do not install this custom component.

## Current build: `2022.12.0b1`

> _You will need to enable beta versions in HACS to see the latest release._

LIFX Beta `2022.12.0b1` _requires_ Home Assistant `2022.12.0b1` to work
effectively. Using this build with Home Assistant 2022.11.0 or older is
most likely going to make your LIFX lights extremely unstable.

If you do have Home Assistant `2022.12.0b1` installed, using this build
should result in significantly faster startup times[^1] for Home Assistant as
well as much faster regular updates, especially of sensor data like RSSI[^2].

### Home Assistant Suggested Area Support

This build will automatically suggest the LIFX group as the suggested area for
a light during config flow. This should improve onboarding for large fleets
of lights.

### Installation

Add <https://github.com/Djelibeybi/ha-lifx-beta> to [HACS](https://hacs.xyz) as
[a new repository](https://hacs.xyz/docs/navigation/stores) in the _Integration_
category. After a few moments, it should appear as a "New Repository" to be
installed.

### Enable debug logging

Adjust your `logger` settings in `configuration.yaml` to enable `debug` for `custom_components.lifx`:

```yaml
logger:
  default: info
  logs:
    custom_components.lifx: debug
```

If you want to report an issue, please collect some debug logs first, then [open a GitHub issue](https://github.com/Djelibeybi/ha-lifx-beta/issues)
and attach the logs. Be sure to review them first so you don't publish anything secret.

## Removal

Remove the integration using HACS but remember to click "ignore" to keep your current config so that the core integration continues to work. You will need to restart to
re-enable the core integration after removal.

## Further documentation

See the [LIFX documentation on the Home Assistant website](https://www.home-assistant.io/integrations/lifx).

[^1]: startup time for my fleet of 60 bulbs has dropped from ~600 seconds to
      ~3.5 seconds.
[^2]: sensor updates are now done every 10 seconds which is three times more
      often than the stable release.
