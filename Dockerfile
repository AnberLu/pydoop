FROM crs4/pydoop-base
MAINTAINER simone.leo@crs4.it

COPY . /build/pydoop
WORKDIR /build/pydoop

RUN source /etc/profile && for v in 2 3; do \
      pip${v} install --upgrade pip && \
      pip${v} install --upgrade -r requirements.txt && \
      python${v} setup.py build && \
      python${v} setup.py install --skip-build; \
    done
