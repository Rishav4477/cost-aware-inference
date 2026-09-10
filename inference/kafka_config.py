import os
import ssl


def kafka_options():
    """Optional TLS/SASL settings shared by every producer and consumer."""
    protocol = os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
    if protocol not in {"PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"}:
        raise ValueError("Invalid KAFKA_SECURITY_PROTOCOL")
    options = {"security_protocol": protocol}
    if "SSL" in protocol:
        options["ssl_context"] = ssl.create_default_context(cafile=os.getenv("KAFKA_CA_FILE"))
    if protocol.startswith("SASL"):
        options.update(
            sasl_mechanism=os.getenv("KAFKA_SASL_MECHANISM", "SCRAM-SHA-512"),
            sasl_plain_username=os.environ["KAFKA_USERNAME"],
            sasl_plain_password=os.environ["KAFKA_PASSWORD"],
        )
    return options
