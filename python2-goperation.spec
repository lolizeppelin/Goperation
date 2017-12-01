%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()"
)}

%{!?_initddir: %{expand: %%global _initddir %{_initrddir}}}

%define python_proj_name Goperation
%define proj_name goperation
%define rundir /var/run/%{proj_name}


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

Requires:       python >= 2.6.6
Requires:       python < 3.0
Requires:       python-redis >= 2.10.0
Requires:       python-simpleservice-ormdb >= 1.0
Requires:       python-simpleservice-ormdb < 1.1
Requires:       python-simpleservice-rpc >= 1.0
Requires:       python-simpleservice-rpc < 1.1

%description
Game operation framework

%files
%defattr(-,root,root,-)
%{python_sitelib}/%{proj_name}/*.py
%{python_sitelib}/%{proj_name}/*.pyc
%{python_sitelib}/%{proj_name}/*.pyo
%{python_sitelib}/%{proj_name}/api/*
%dir %{python_sitelib}/%{proj_name}/cmd/
%{python_sitelib}/%{proj_name}/cmd/db/*
%dir %{python_sitelib}/%{proj_name}/filemanager/
%{python_sitelib}/%{proj_name}/filemanager/*
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
%{python_sitelib}/%{proj_name}/manager/utils/*.py
%{python_sitelib}/%{proj_name}/manager/utils/*.pyc
%{python_sitelib}/%{proj_name}/manager/utils/*.pyo
%{python_sitelib}/%{proj_name}/manager/utils/*
%{python_sitelib}/%{proj_name}-%{version}-*.egg-info/*
%dir %{python_sitelib}/%{proj_name}-%{version}-*.egg-info/
%doc README.rst
%doc doc/*
%config %{_sysconfdir}/%{proj_name}/goperation.conf
%config %{_sysconfdir}/%{proj_name}/endpoints/*.conf



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

%config %{_sysconfdir}/%{proj_name}/gcenter.conf.sample
%config %{_sysconfdir}/%{proj_name}/gcenter-paste.ini.sample


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
%config %{_sysconfdir}/%{proj_name}/agent.conf.sample



%package application
Summary:        Goperation application agent
Group:          Development/Libraries
Requires:       %{name}-agent == %{version}

%description application
goperation application agent

%files application
%defattr(-,root,root,-)
%{python_sitelib}/%{proj_name}/cmd/agent/application.py*
%dir %{python_sitelib}/%{proj_name}/manager/rpc/agent/application/
%{python_sitelib}/%{proj_name}/manager/rpc/agent/application/*



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


%prep
%setup -q -n %{proj_name}-%{version}
rm -rf %{proj_name}.egg-info

%build
%{__python} setup.py build

%install
%{__rm} -rf %{buildroot}
%{__python} setup.py install -O1 --skip-build --root %{buildroot}

install -C -D etc/*.conf.sample -d %{buildroot}%{_sysconfdir}/%{proj_name}
install -C -D etc/gcenter-paste.ini -d %{buildroot}%{_sysconfdir}/%{proj_name}
install -d %{buildroot}%{_sysconfdir}/%{proj_name}/endpoints
install -d %{rundir}

install  -p -D -m 0755 gcenter-wsgi %{buildroot}%{_initrddir}/gcenter-wsgi
install  -p -D -m 0755 gcenter-rpc %{buildroot}%{_initrddir}/gcenter-rpc
install  -p -D -m 0755 gop-application %{buildroot}%{_initrddir}/gop-application
install  -p -D -m 0755 gop-scheduler %{buildroot}%{_initrddir}/gop-scheduler

install  -p -D -m 0554 bin/* %{buildroot}%{_sbindir}

%clean
%{__rm} -rf %{buildroot}



%post server
%if %{initscripttype} == "systemd"
%systemd_post gcenter-wsgi.service
%systemd_post gcenter-rpc.service
%endif
%if %{initscripttype} == "sysv"
chkconfig --add gcenter-wsgi
chkconfig --add gcenter-rpc
%endif

%preun server
chkconfig --del gcenter-wsgi
chkconfig --del gcenter-rpc



%post application
%if %{initscripttype} == "systemd"
%systemd_post gop-application.service
%endif
%if %{initscripttype} == "sysv"
chkconfig --add gop-application
%endif

%preun application
chkconfig --del gop-application



%post scheduler
%if %{initscripttype} == "systemd"
%systemd_post gop-scheduler.service
%endif
%if %{initscripttype} == "sysv"
chkconfig --add gop-scheduler
%endif

%preun application
chkconfig --del gop-scheduler


%changelog

* Mon Aug 29 2017 Lolizeppelin <lolizeppelin@gmail.com> - 1.0.0
- Initial Package