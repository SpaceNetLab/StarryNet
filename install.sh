#!/usr/bin/env bash

# installation script for Ubuntu, Debian and CentOS
# author: Yangtao Deng

DIST=Unknown
RELEASE=Unknown
CODENAME=Unknown
ARCH=`uname -m`
if [ "$ARCH" = "x86_64" ]; then ARCH="amd64"; fi
if [ "$ARCH" = "i686" ]; then ARCH="i386"; fi

test -e /etc/debian_version && DIST="Debian"
grep Ubuntu /etc/lsb-release &> /dev/null && DIST="Ubuntu"
if [ "$DIST" = "Ubuntu" ] || [ "$DIST" = "Debian" ]; then
    # Truly non-interactive apt-get installation
    install='sudo DEBIAN_FRONTEND=noninteractive apt-get -y -q install'
    remove='sudo DEBIAN_FRONTEND=noninteractive apt-get -y -q remove'
    pkginst='sudo dpkg -i'
    update='sudo apt-get'
    # Prereqs for this script
    if ! which lsb_release &> /dev/null; then
        $install lsb-release
    fi
fi
test -e /etc/fedora-release && DIST="Fedora"
test -e /etc/redhat-release && DIST="RedHatEnterpriseServer"
if [ "$DIST" = "Fedora" -o "$DIST" = "RedHatEnterpriseServer" ]  || [ "$DIST" = "CentOS" ]; then
    install='sudo yum -y install'
    remove='sudo yum -y erase'
    pkginst='sudo rpm -ivh'
    update='sudo yum'
    # Prereqs for this script
    if ! which lsb_release &> /dev/null; then
        $install redhat-lsb-core
    fi
fi

echo "Installing dependencies"
$install python3 python-setuptools python3-pip
$install docker-ce docker-ce-cli containerd.io
sudo python3 -m pip install --upgrade pip
sudo python3 -m pip install -r tools/requirements.txt
sudo python3 setup.py install