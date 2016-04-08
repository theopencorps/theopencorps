TheOpenCorps
============

A regression-as-a-service project tracker for RTL development.


Overview
--------

We use Travis-CI to run simulation and synthesis each check-in.  We
keep track of results, coverage, resource utilisation and make these
available via:

* E-mail notifications
* Github Commit status annotations
* Raw API access to the database
* Project webpage summarising the result history
* Shields.io badge generation

The goal is to be tool / workflow agnostic.

How it works
------------

* Users post their code on github
* Tell TheOpenCorps to start tracking their project
* We expect to find an `.opencorps.yml` in root of the project describing the workflow
* Simulation and synthesis will be run every check-in
* Browse the results


Workflows
---------

* [ ] [Cocotb](https://github.com/potentialventures/cocotb)
* [ ] [FuseSoc](https://github.com/olofk/fusesoc)
* [ ] [VUnit](https://github.com/VUnit/vunit)
* [ ] [MyHDL](http://www.myhdl.org/)
* [ ] [SVUnit](http://www.agilesoc.com/open-source-projects/svunit/)
* [ ] [OSVVM](http://osvvm.org/)
* [ ] [ChipTools](https://github.com/pabennett/chiptools)


Tooling
-------

* [ ] [Aldec Riviera-PRO (EDU)](https://www.aldec.com/en/products/functional_verification/riviera-pro)
* [ ] [Altera Quartus](https://www.altera.com)
* [ ] [Yosys Open Source Synthesis](http://www.clifford.at/yosys/)
* [ ] [Icarus Verilog](http://iverilog.icarus.com/)
* [ ] [Verilator](http://www.veripool.org/wiki/verilator)


