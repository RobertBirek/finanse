FROM frooodle/s-pdf@sha256:3b3670fce70b396ec56ba380a3cc7858e0abf83fe13f31c88f7737847763a396
USER 0:0
COPY patch_init.py /tmp/patch_init.py
COPY --chown=0:0 --chmod=0444 validate_runtime_paths.py /scripts/validate_runtime_paths.py
RUN python3 /tmp/patch_init.py /scripts/init-without-ocr.sh \
 && rm /tmp/patch_init.py \
 && for alias in diagnostics stirling-diagnostics diag debug diagnostic; do \
      ln -sf /scripts/stirling-diagnostics.sh /usr/local/bin/$alias; done \
 && for alias in aot-diag aot-diagnostics; do \
      ln -sf /scripts/aot-diagnostics.sh /usr/local/bin/$alias; done
COPY --chown=0:0 --chmod=0444 pol.traineddata /usr/share/tesseract-ocr/5/tessdata/pol.traineddata
COPY --chown=0:0 --chmod=0444 TESSDATA_LICENSE /usr/share/doc/tessdata-pol/LICENSE
RUN echo 'c4476cdbc0e33d898d32345122b7be1cbf85ace15f920f06c7714756e1ef79b2  /usr/share/tesseract-ocr/5/tessdata/pol.traineddata' | sha256sum -c -
ENV HOME=/tmp/stirling-home STIRLING_AOT_ENABLE=false
USER 1001:1001
