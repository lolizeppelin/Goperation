%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()"
)}

%{!?_initddir: %{expand: %%global _initddir %{_initrddir}}}

%define python_proj_name Goperation
%define proj_name goperation
%global rundir /var/run/%{proj_name}
%global logdir /var/log/%{proj_name}


%define _release RELEASEVERSION

Name:           python-%{proj_name}
Version:        RPMVERSION
Release:        %{_release}%{?dist}
Summary:        Game operation framework
Group:          Development/Libraries
License:        MPLv1.1 or GPLv2
URL:            http://github.com/Lolizeppelin/%{python_proj_name}
Source0:        %{proj_name}-%{version}.tar.gz
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildArch:      noarch

BuildRequires:  python-setuptools >= 11.0
BuildRequires:  python-simpleutil

Requires:       python >= 2.6.6
Requires:       python < 3.0
Requires:       python-redis >= 2.10.0
Requires:       python-simpleservice-ormdb >= 1.0
Requires:       python-simpleservice-ormdb < 1.1
Requires:       python-simpleservice-rpc >= 1.0
Requires:       python-simpleservice-rpc < 1.1
Requires:       python-psutil >= 5.4.0
Requires:       python-websockify >= 0.8.0


%description
Game operation framework

%files
%defattr(-,root,root,-)
%{python_sitelib}/%{proj_name}/*.py
%{python_sitelib}/%{proj_name}/*.pyc
%{python_sitelib}/%{proj_name}/*.pyo
%{python_sitelib}/%{proj_name}/api/*
%dir %{python_sitelib}/%{proj_name}/cmd/
%dir %{python_sitelib}/%{proj_name}/cmd/__init__.py*
%{python_sitelib}/%{proj_name}/cmd/db/*
%dir %{python_sitelib}/%{proj_name}/filemanager/
%{python_sitelib}/%{proj_name}/filemanager/*
%dir %{python_sitelib}/%{proj_name}/websocket/
%{python_sitelib}/%{proj_name}/websocket/*
%dir %{python_sitelib}/%{proj_name}/redis/
%{python_sitelib}/%{proj_name}/redis/*
%dir %{python_sitelib}/%{proj_name}/taskflow/
%{python_sitelib}/%{proj_name}/taskflow/*
%dir %{python_sitelib}/%{proj_name}/manager/
%{python_sitelib}/%{proj_name}/manager/*.py
%{python_sitelib}/%{proj_name}/manager/*.pyc
%{python_sitelib}/%{proj_name}/manager/*.pyo
%dir %{python_sitelib}/%{proj_name}/manager/rpc/
%{python_sitelib}/%{proj_name}/manager/rpc/*.py
%{python_sitelib}/%{proj_name}/manager/rpc/*.pyo
%{python_sitelib}/%{proj_name}/manager/rpc/*.pyc
%dir %{python_sitelib}/%{proj_name}/manager/utils/
%{python_sitelib}/%{proj_name}/manager/utils/*
%{python_sitelib}/%{proj_name}-%{version}-*.egg-info/*
%dir %{python_sitelib}/%{proj_name}-%{version}-*.egg-info/
%{_sysconfdir}/%{proj_name}/goperation.conf.sample
%{_bindir}/gop-websocket
%dir %{_sysconfdir}/%{proj_name}/
%dir %{_sysconfdir}/%{proj_name}/endpoints/
%dir %{logdir}
%dir %{rundir}
%doc README.md
%doc doc/*



%package server
Summary:        Control center of goperation
Group:          Development/Libraries
Requires:       %{name} == %{version}
Requires:       python-simpleservice-wsgi >= 1.0
Requires:       python-simpleservice-wsgi < 1.1

%description server
goperation wsgi server and rpc server

%files server
%defattr(-,root,root,-)
%{python_sitelib}/%{proj_name}/cmd/server/*
%{python_sitelib}/%{proj_name}/manager/rpc/server/
%{python_sitelib}/%{proj_name}/manager/wsgi/*
%{_sysconfdir}/%{proj_name}/gcenter.conf.sample
%{_sysconfdir}/%{proj_name}/gcenter-paste.ini.sample
%{_initrddir}/gcenter-rpc
%{_initrddir}/gcenter-wsgi
%{_sbindir}/gcenter-rpc
%{_sbindir}/gcenter-wsgi
%{_sbindir}/gcenter-db-init


%package agent
Summary:        Control center of goperation
Group:          Development/Libraries
Requires:       %{name} == %{version}

%description agent
goperation rpc agent

%files agent
%defattr(-,root,root,-)
%dir %{python_sitelib}/%{proj_name}/cmd/agent
%{python_sitelib}/%{proj_name}/cmd/agent/__init__.py*
%dir %{python_sitelib}/%{proj_name}/manager/rpc/agent/
%{python_sitelib}/%{proj_name}/manager/rpc/agent/*.py
%{python_sitelib}/%{proj_name}/manager/rpc/agent/*.pyc
%{python_sitelib}/%{proj_name}/manager/rpc/agent/*.pyo
%{_sysconfdir}/%{proj_name}/agent.conf.sample



%package application
Summary:        Goperation application agent
Group:          Development/Libraries
Requires:       %{name}-agent == %{version}
Requires:       python-simpleflow >= 1.0
Requires:       python-simpleflow < 1.1

%description application
goperation application agent

%files application
%defattr(-,root,root,-)
%{python_sitelib}/%{proj_name}/cmd/agent/application.py*
%dir %{python_sitelib}/%{proj_name}/manager/rpc/agent/application/
%{python_sitelib}/%{proj_name}/manager/rpc/agent/application/*
%{_initrddir}/gop-application
%{_sbindir}/gop-application



%package scheduler
Summary:        Goperation scheduler agent
Group:          Development/Libraries
Requires:       %{name}-agent == %{version}

%description scheduler
goperation scheduler agent

%files scheduler
%defattr(-,root,root,-)
%dir %{python_sitelib}/%{proj_name}/manager/rpc/agent/scheduler/
%{python_sitelib}/%{proj_name}/manager/rpc/agent/scheduler/*
%{python_sitelib}/%{proj_name}/cmd/agent/scheduler.py*
%{_initrddir}/gop-scheduler
%{_sbindir}/gop-scheduler


%prep
%setup -q -n %{proj_name}-%{version}
rm -rf %{proj_name}.egg-info

%build
%{__python} setup.py build

%install
%{__rm} -rf %{buildroot}
%{__python} setup.py install -O1 --skip-build --root %{buildroot}

install -d %{buildroot}%{rundir}
install -d %{buildroot}%{logdir}
install -d %{buildroot}%{_sysconfdir}/%{proj_name}/endpoints
install -p -D -m 0644 etc/*.conf.sample %{buildroot}%{_sysconfdir}/%{proj_name}
install -p -D -m 0644 etc/*.ini.sample %{buildroot}%{_sysconfdir}/%{proj_name}


install -d %{buildroot}%{_initrddir}
install -p -D -m 0755 gcenter-wsgi %{buildroot}%{_initrddir}/gcenter-wsgi
install -p -D -m 0755 gcenter-rpc %{buildroot}%{_initrddir}/gcenter-rpc
install -p -D -m 0755 gop-application %{buildroot}%{_initrddir}/gop-application
install -p -D -m 0755 gop-scheduler %{buildroot}%{_initrddir}/gop-scheduler

install -d %{buildroot}%{_sbindir}
install -d %{buildroot}%{_bindir}
install -p -D -m 0754 sbin/* %{buildroot}%{_sbindir}
install -p -D -m 0754 bin/* %{buildroot}%{_bindir}

%clean
%{__rm} -rf %{buildroot}


%post server
chkconfig --add gcenter-wsgi
chkconfig --add gcenter-rpc
%preun server
chkconfig --del gcenter-wsgi
chkconfig --del gcenter-rpc

%post application
chkconfig --add gop-application
%preun application
chkconfig --del gop-application

%post scheduler
chkconfig --add gop-scheduler
%preun scheduler
chkconfig --del gop-scheduler


%changelog

* Mon Aug 29 2017 Lolizeppelin <lolizeppelin@gmail.com> - 1.0.0
- Initial Package