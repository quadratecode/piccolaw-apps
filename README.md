# About

A web app to check the temporal validity of your termination and to calculate any possible embargo, notice and sick pay periods under Swiss law. Built with Python and [PyWebIO](https://github.com/pywebio/PyWebIO). Hosted [here](https://www.obiter.ch/tools/work-calc/). Currently undergoing beta testing.

# Features

## Implemented

- [x] Permanent full-time employment (100 %)
- [x] Incapacities due to illness or accident
- [x] The probation period duration incl. a possible extension considering legally mandated holidays
- [x] The validity of a termination with regards to the embargo period
- [x] The embargo period duration
- [x] The notice period duration incl. a possible extension
- [x] Leap years are respected
- [x] Changes in seniority during an incapacity are respected
- [x] Optionality of certain inputs
- [x] User defined inputs
- [x] Different incapacities to work (e.g. military service) and combinations thereof
- [x] Single or multiple incapacity with gaps

## Planned

- [ ] Calculate possible reductions in vacation days
- [ ] Further expand user defined inputs
- [ ] Further improve layout and explanation of output
- [ ] Allow mixing of different incapacity types
- [ ] Quality testing

# Contribute

- If your input returns an error or incorrect results, please open an [issue](https://github.com/quadratecode/ch-termination-calc/issues) containing your input data
- For questions and feature requests, please use [GitHub discussions](https://github.com/quadratecode/ch-termination-calc/discussions)
- PRs are welcomed. Since this project is licensed under the EUPL (v1.2 only, with specific provisions), your contributions must be under a compatible license. By contributing code or other assets to the project, you confirm that you hold the necessary rights for these contributions.
