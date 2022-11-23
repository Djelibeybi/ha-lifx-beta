# LIFX Beta for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

**WARNING**: This is an unstable release. Do not install in a live or production
system.

This is a pre-release/testing version of the core LIFX integration. This repo
exists purely to make it easier to install the test version via HACS instead of
having to do it manually.

**WARNING**: if you prefer stability, do not install this custom component.

This custom component uses a different mechanism for initial bulb configuration
as well as a different approach to regular updates from each device. The goal
is to try and find the most reliable way of updating all devices without any
timeouts (or as few as possible).

## Installation

Add <https://github.com/Djelibeybi/ha-lifx-beta> to [HACS](https://hacs.xyz) as
[a new repository](https://hacs.xyz/docs/navigation/stores) in the _Integration_
category. After a few moments, it should appear as a "New Repository" to be
installed.

## Enable debug logging

Adjust your `logger` settings in `configuration.yaml` to enable `debug` for `custom_components.lifx`:

```yaml
logger:
  default: info
  logs:
    custom_components.lifx: debug
```

If you want to report an issue, please collect some debug logs first, then [open a GitHub issue](https://github.com/Djelibeybi/ha-lifx-beta/issues)
and attach the logs. Be sure to review them first so you don't publish anything secret.

## Further documentation

See the [LIFX documentation on the Home Assistant website](https://www.home-assistant.io/integrations/lifx).
