# LIFX Beta for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

**WARNING**: This is an unstable release. Do not install in a live or production
system.

This is a pre-release/testing version of the core LIFX integration. This repo
exists purely to make it easier to install the test version via HACS instead of
having to do it manually.

**WARNING**: if you prefer stability, do not install this custom component.

## Current build: `2022.12.4`

It's best to run LIFX Beta `2022.12.4` with Home Assistant `2022.12.0` or newer.
Using this build with Home Assistant 2022.11.0 or older is more likely
to result in your LIFX lights becoming unavailable.

This release includes the latest LIFX themes from the updated LIFX smartphone
app v4.13.0 and resolves a bug with the LIFX pulse service when run against
LIFX white bulbs.

If you do have Home Assistant `2022.12.0` or newer installed, using this build
should result in significantly faster startup times[^1] for Home Assistant, more
reliable connectivity with fewer bulbs becoming unavailable (and that should be
less often) as well as more responsive updates, especially of sensor data like RSSI[^2].

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

> Note: Only enable debug logging if you're experiencing a problem and need to
> log an issue.

To enable debug logging, adjust your `logger` settings in `configuration.yaml`
and specify `debug` for `custom_components.lifx`:

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

[^1]: startup time for my fleet of 60 bulbs has dropped from ~60-90 seconds to
      ~3.5 seconds.
[^2]: sensor updates are now done every 10 seconds which is three times more
      often than the stable release.
