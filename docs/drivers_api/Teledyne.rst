.. _teledyne_api:

Teledyne LeCroy Drivers
======================

The T3PS30051P driver exposes one programmable 30 V / 5 A output directly on the
instrument. The T3PS3000 driver exposes two programmable 32 V / 3.2 A outputs as
``ch1`` and ``ch2``, along with timer sequences, tracking modes, and LAN settings.
Its third output, ``ch3``, supports remote on/off control but not output readback
or voltage selection; voltage is selected on the front panel.

The ``voltage`` and ``current`` parameters represent programmed setpoints.
``measured_voltage``, ``measured_current``, and ``measured_power`` represent
read-only measurements. Neither construction nor closing a driver changes the
output settings.

The T3PS30051P does not respond to ``*IDN?``. Its ``IDN`` parameter returns the
known vendor and model, with ``None`` for the serial number and firmware,
without communicating with the supply. This also avoids identification queries
during construction and station snapshots; the connection message is not a
hardware identification check. Queries use a one-second delay before reading
the response, matching the standalone driver.

Examples:

* :doc:`T3PS30051P </examples/driver_examples/Qcodes example with Teledyne T3PS30051P>`
* :doc:`T3PS3000 </examples/driver_examples/Qcodes example with Teledyne T3PS3000>`

.. automodule:: qcodes.instrument_drivers.teledyne
    :autosummary:
    :no-inherited-members:
