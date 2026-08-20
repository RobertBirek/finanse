from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]


def test_ingress_network_contract_isolated_from_shared_proxy() -> None:
    contract = (REPOSITORY_ROOT / "ops" / "ingress-network-contract.yaml").read_text()

    assert "name: finanse_ingress" in contract
    assert "subnet: 172.24.0.0/24" in contract
    assert "npmplus: 172.24.0.2" in contract
    assert "finanse-frontend: [finanse_ingress, finanse_internal]" in contract
    assert "finanse-backend: [finanse_internal]" in contract
    assert "shared_proxy: []" in contract


def test_frontend_trusts_only_the_dedicated_npmplus_ingress_ip() -> None:
    config = (REPOSITORY_ROOT / "frontend" / "nginx.conf").read_text()

    assert "set_real_ip_from 172.24.0.2;" in config
    assert "172.22.0.0/16" not in config
