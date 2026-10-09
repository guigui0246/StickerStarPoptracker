# Third-party compiler

`gibberish/` is the unmodified local Gibberish compiler snapshot used for the
native patch builds. Its MIT license and copyright notice are included in
`gibberish/LICENSE`. It contains compiler code, not ROM content or game assets.

The generator selects this copy by default, so users do not need to find a
compiler or run a separate patch application command. `--compiler` overrides
it for compiler development. Release builds include it as a data dependency.
The existing `compiler_driver.py` applies compatibility fixes at runtime.
