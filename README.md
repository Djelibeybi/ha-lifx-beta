# LIFX Beta for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

This is a pre-release/testing version of the core LIFX integration. This repo
exists purely to make it easier to install the test version via HACS instead of
having to do it manually.

## Current version: `2023.1.0b5`

This release will never offline a bulb. Essentially, instead of raising an exception when an empty response is received (which is what happens when the bulb just doesn't respond), it will send a debug log with a message instead.

_The goal of this release is to get your subjective opinion on the stability of your LIFX bulbs._

My assumption after limited testing on my own fleet is that most folks won't actually notice when a bulb doesn't respond because the integration will either try again or something else will happen and the bulb will respond again soon enough.

_Please use the release discussion topic to provide feedback on how your fleet reponds._

### Changes from 2023.1.0.b4

* log empty responses instead of raising exceptions


### Changes from 2023.1.0b2

* refactor the way connections are managed and recreate connections if the device stops responding.
* limit the number of inflight messages per device.

As always, `DEBUG` logging is _very, very noisy._ Only enable it if you're having a particular problem and need to open an issue.

### Changes from 2023.1.0b1

* Minor fix to make the `lifx.set_hev_cycle_state` service work as expected.

### Changes from 2022.12.1

This first (ish) new LIFX Beta version in 2023 drops almost everything I was testing in the previous beta and uses a new technique I'm hoping is as effective in your setups as it has been on mine. This version also increases the update rate for all sensors to every 10 seconds as the integration now updates everything all at once.

### Additional changes

This release includes the latest LIFX themes from the updated LIFX smartphone
app v4.13.0 and resolves a bug with the LIFX pulse service when run against
LIFX white bulbs.

### Suggested Area Support

This build will automatically suggest the LIFX group as the suggested area for
a light during config flow. This should improve onboarding for large fleets
of lights.

### Installation

Add <https://github.com/Djelibeybi/ha-lifx-beta> to [HACS](https://hacs.xyz) as
[a new repository](https://hacs.xyz/docs/navigation/stores) in the *Integration*
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

If you want to report an issue, please collect some debug logs first, then
[open a GitHub issue](https://github.com/Djelibeybi/ha-lifx-beta/issues)
and attach the logs. Be sure to review them first so you don't publish anything secret.

## Removal

Remove the integration using HACS but remember to click "ignore" to keep your
current config so that the core integration continues to work. You will need to
restart to re-enable the core integration after removal.

## Further documentation

See the [LIFX documentation on the Home Assistant website](https://www.home-assistant.io/integrations/lifx).
