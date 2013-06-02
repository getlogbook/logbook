# -*- mode: ruby -*-
# vi: set ft=ruby :
PYTHON_VERSIONS = ["python2.6", "python2.7", "python3.3"]

Vagrant::Config.run do |config|
  config.vm.define :box do |config|
    config.vm.box = "precise64"
    config.vm.box_url = "http://files.vagrantup.com/precise64.box"
    config.vm.host_name = "box"
    config.vm.provision :shell, :inline => "sudo apt-get -y update"
    config.vm.provision :shell, :inline => "sudo apt-get install -y python-software-properties"
    config.vm.provision :shell, :inline => "sudo add-apt-repository -y ppa:fkrull/deadsnakes"
    config.vm.provision :shell, :inline => "sudo apt-get update"
    PYTHON_VERSIONS.each { |python_version|
      config.vm.provision :shell, :inline => "sudo apt-get install -y " + python_version + " " + python_version + "-dev"
    }
    config.vm.provision :shell, :inline => "sudo apt-get install -y libzmq-dev wget libbluetooth-dev libsqlite3-dev"
    config.vm.provision :shell, :inline => "wget http://python-distribute.org/distribute_setup.py -O /tmp/distribute_setup.py"
    PYTHON_VERSIONS.each { |python_executable|
      config.vm.provision :shell, :inline => python_executable + " /tmp/distribute_setup.py"
    }
    config.vm.provision :shell, :inline => "sudo easy_install tox==1.2"
    config.vm.provision :shell, :inline => "sudo easy_install virtualenv==1.6.4"
  end
end
