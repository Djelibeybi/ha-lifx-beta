# LIFX (Beta)

This is a beta version of the built-in LIFX integration that includes
a new discovery method that should result in more consistent bulb detection.

## How to install

Add <https://github.com/Djelibeybi/ha-lifx-beta> to [HACS](https://hacs.xyz) as
a custom repository and then install the Beta integration when it appears.

## How to get debug logs

Adjust your `logger` settings in `configuration.yaml` to get debug logs:

```yaml
logger:
  default: info
  logs:
    custom_components.lifx: debug
```

Then, [open a GitHub issue](https://github.com/Djelibeybi/ha-lifx-beta/issues) and attach
the logs. Be sure to review them first so you don't publish anything secret.
