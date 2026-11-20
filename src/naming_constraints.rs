//! OpenID Federation §6.2.2 host restrictions on subordinate entity IDs.
use anyhow::{Result, anyhow, ensure};
use serde_json::Value;
use url::Url;

/// Host rules from one superior. An absent permitted list allows any host
/// that passes the exclusions, while an empty permitted list allows none.
#[derive(Debug, Default, Clone)]
pub struct NamingConstraints {
    permitted: Option<Vec<String>>,
    excluded: Vec<String>,
}

/// Check the DNS length limits and ASCII hostname label syntax.
fn valid_dns_name(domain: &str) -> bool {
    domain.len() <= 253
        && domain.split('.').all(|label| {
            !label.is_empty()
                && label.len() <= 63
                && !label.starts_with('-')
                && !label.ends_with('-')
                && label
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b == b'-')
        })
}

impl NamingConstraints {
    /// Parse both lists, retaining a leading dot to distinguish a subtree rule.
    pub(crate) fn parse(value: &Value) -> Result<Self> {
        let object = value
            .as_object()
            .ok_or_else(|| anyhow!("naming_constraints must be an object"))?;
        let names = |member: &str| -> Result<Option<Vec<String>>> {
            let Some(value) = object.get(member) else {
                return Ok(None);
            };
            let entries = value
                .as_array()
                .ok_or_else(|| anyhow!("naming_constraints.{member} must be an array"))?;
            entries
                .iter()
                .map(|value| {
                    let name = value
                        .as_str()
                        .ok_or_else(|| anyhow!("expected a DNS name in {member}"))?;
                    let name = name.strip_suffix('.').unwrap_or(name);
                    let domain = name.strip_prefix('.').unwrap_or(name);
                    ensure!(
                        valid_dns_name(domain),
                        "invalid DNS name in naming_constraints.{member}"
                    );
                    Ok(name.to_ascii_lowercase())
                })
                .collect::<Result<Vec<_>>>()
                .map(Some)
        };
        Ok(Self {
            permitted: names("permitted")?,
            excluded: names("excluded")?.unwrap_or_default(),
        })
    }

    /// Check the host of a subordinate entity ID, giving exclusions precedence.
    pub(crate) fn check(&self, entity: &str) -> Result<()> {
        let url = Url::parse(entity)?;
        let host = url
            .host_str()
            .ok_or_else(|| anyhow!("missing host in entity ID"))?;
        let host = host.strip_suffix('.').unwrap_or(host);
        if let Some(url::Host::Domain(_)) = url.host() {
            ensure!(valid_dns_name(host), "invalid DNS host in entity ID");
        }
        // URL parsing canonicalizes DNS case and IDNA. A leading dot includes
        // the label boundary and requires at least one label before it.
        let matches = |name: &String| {
            if name.starts_with('.') {
                host.len() > name.len() && host.ends_with(name)
            } else {
                host == name
            }
        };
        ensure!(
            !self.excluded.iter().any(matches),
            "entity host {host} is excluded"
        );
        if let Some(permitted) = &self.permitted {
            ensure!(
                permitted.iter().any(matches),
                "entity host {host} is outside permitted names"
            );
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    /// Exercise label boundaries, host normalization, and exclusion precedence.
    #[test]
    fn dns_subtrees_use_host_labels_and_exclusions_take_priority() {
        let rules = NamingConstraints::parse(&json!({"permitted": [".Example.EDU", "exact.test"], "excluded": ["blocked.example.edu"]})).unwrap();
        for entity in [
            "https://a.b.example.edu:8443/path",
            "https://EXACT.test./path",
        ] {
            assert!(rules.check(entity).is_ok(), "{entity}");
        }
        for entity in [
            "https://example.edu",
            "https://notexample.edu",
            "https://sub.exact.test",
            "https://a..example.edu",
            "https://exact.test..",
            "https://blocked.example.edu.",
            "https://other.test/a.example.edu",
        ] {
            assert!(rules.check(entity).is_err(), "{entity}");
        }
    }
}
