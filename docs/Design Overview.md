
# SimpleSight

## Open-Source Intelligence & Digital Footprint Intelligence Platform

**Product Family:** SimpleSuite  
**Developer:** Summit Cyber Group, LLC  
**Tagline:** See What Others Miss.  
**Product Type:** Multi-tenant SaaS  
**Status:** Proposed for development

---

## 1. Executive Overview

SimpleSight is an AI-assisted Open-Source Intelligence (OSINT) platform designed to discover, collect, correlate, and analyze publicly available intelligence about organizations and their digital footprints.

The platform transforms traditional manual OSINT investigations into automated, repeatable, and actionable assessments.

SimpleSight will enable security professionals, penetration testers, risk managers, and organizations to understand what information about their infrastructure, technology, personnel, and operations is publicly discoverable.

Unlike standalone OSINT utilities, SimpleSight will integrate with the SimpleSuite ecosystem to transform intelligence into security findings, risk assessments, and remediation workflows.

**Primary objective:** Turn publicly available information into actionable security intelligence.

## 2. Target Audience

- Penetration testing and red team professionals
    
- Managed security service providers (MSSPs)
    
- Corporate security and threat intelligence teams
    
- Virtual CISOs and security consultants
    
- Organizations performing digital exposure assessments
    
- Third-party and vendor risk assessment teams
    

## 3. Core Product Capabilities

### 3.1 Organization Intelligence

Discover and correlate publicly available information about an organization.

Capabilities include:

- Organization names, aliases, and related entities
    
- Subsidiaries and parent organizations
    
- Public business registration details
    
- Public office and operational locations
    
- Published business contact details
    
- Public organizational structures
    
- Public third-party relationships
    
- Publicly advertised products and services
    

### 3.2 Digital Infrastructure Discovery

Map an organization's publicly discoverable technical footprint.

Capabilities include:

- Domain and subdomain discovery
    
- DNS records and infrastructure relationships
    
- Certificate transparency intelligence
    
- Public IP address and ASN associations
    
- Hosting and cloud provider identification
    
- Public-facing technology fingerprinting
    
- Internet-exposed service intelligence
    
- Historical domain records
    
- Archived website intelligence
    
- Publicly discoverable cloud storage references
    

Active probing must require explicit authorization and be separately controlled from passive OSINT collection.

### 3.3 Personnel and Social Intelligence

Identify public organizational information relevant to security exposure.

Capabilities include:

- Public employee and leadership profiles
    
- Published organizational roles
    
- Public professional networking information
    
- Published corporate email addresses
    
- Organizational email naming patterns
    
- Public technology recruitment intelligence
    
- Publicly disclosed administrative and technical roles
    

Personnel information must be restricted to legitimate organizational security use cases. The platform must enforce appropriate privacy protections, retention limits, and source restrictions.

### 3.4 Information Exposure Discovery

Identify potentially sensitive information disclosed through publicly available sources.

Capabilities include:

- Publicly indexed sensitive documents
    
- Exposed configuration references
    
- Public repository secret indicators
    
- Publicly exposed storage references
    
- Archived sensitive content
    
- Public credential exposure indicators
    
- Potentially exposed internal infrastructure references
    
- Metadata extracted from publicly accessible documents
    

Do not retrieve, display, or retain secret values unnecessarily. Findings should use redacted evidence and support safe remediation.

### 3.5 Intelligence Correlation

Aggregate discovered intelligence into a unified organizational intelligence model.

Capabilities include:

- Entity relationship mapping
    
- Domain-to-organization correlation
    
- Technology-to-infrastructure mapping
    
- Third-party dependency relationships
    
- Duplicate discovery consolidation
    
- Historical intelligence comparison
    
- Confidence scoring
    
- Exposure prioritization
    
- AI-assisted finding explanations
    

Every finding must maintain source provenance, collection timestamps, supporting evidence, and confidence levels.

## 4. Test Case Coverage

The initial development scope maps directly to the 23 test cases supplied for this project.

|Test Case|Category|Implementation|
|---|---|---|
|OSINT001|Open-Source Intelligence PREVIEW|Assessment overview and summary dashboard|
|OSINT002|OSINT Methodology|Repeatable investigation workflows|
|OSINT003|Business Investigation|Business intelligence discovery|
|OSINT004|Organization|Organizational entity profiling|
|OSINT005|Locations|Public geographic and office information|
|OSINT006|Staff|Public personnel intelligence|
|OSINT007|Contact Information|Published business contact discovery|
|OSINT008|Business Records|Public corporate record discovery|
|OSINT009|Services|Published business services|
|OSINT010|Social Networks|Public organizational social presence|
|OSINT011|Domain Information|Domain registration and DNS intelligence|
|OSINT012|Public Domain Records|Historical and public domain records|
|OSINT013|Domain Structure|Subdomain and DNS relationship discovery|
|OSINT014|Cloud Storage|Public cloud storage exposure indicators|
|OSINT015|Email Addresses|Public organizational email discovery|
|OSINT016|Third Parties|Public vendor and partner relationships|
|OSINT017|Compounded Networks|Related network and infrastructure correlation|
|OSINT018|Technologies in Use|Public technology fingerprinting|
|OSINT019|Leaked Information|Public information exposure indicators|
|OSINT020|Archives|Historical web and document intelligence|
|OSINT021|Internal Leaks|Publicly exposed internal-information indicators|
|OSINT022|Breaches|Breach intelligence integration with SimpleShadow|
|OSINT023|Intelligence|Correlated intelligence summaries|

**Source note:** The uploaded CSV provides test case names and identifiers, not detailed procedures or acceptance criteria. The functionality described above is the proposed product interpretation of those categories.

## 5. User Experience and Dashboards

### Main Dashboard

Display:

- Total monitored organizations
    
- Discovered domains and subdomains
    
- Infrastructure assets
    
- Public organizational intelligence
    
- Information exposure findings
    
- New discoveries since previous scans
    
- High-priority intelligence
    
- Historical exposure trends
    

### Investigation Workspace

Users can create an investigation by entering:

1. Organization name
    
2. Primary domain
    
3. Additional known domains
    
4. Investigation scope
    
5. Authorized assessment type
    

The platform automatically builds a discovery plan and runs supported collectors.

### Intelligence Explorer

Provide an interactive relationship visualization connecting:

- Organizations
    
- Domains
    
- Infrastructure
    
- Technologies
    
- Public personnel references
    
- Third-party relationships
    
- Exposure findings
    

Users should be able to click any entity to view supporting intelligence and evidence.

### Findings Management

Every actionable finding must support:

- Severity and confidence
    
- Discovery timestamp
    
- Supporting source references
    
- Affected assets
    
- Business impact
    
- AI-generated explanation
    
- Remediation recommendations
    
- Status and ownership
    
- Export and SimpleCISO integration
    

## 6. AI Intelligence Engine

SimpleSight will use AI to assist with:

- Correlating intelligence across multiple public sources
    
- Identifying potential relationships
    
- Summarizing investigation results
    
- Explaining potential organizational risks
    
- Prioritizing validated exposure findings
    
- Producing executive summaries
    
- Recommending further investigation
    
- Generating remediation guidance
    

**AI must not invent findings.** Every reported discovery must link to verifiable source evidence. AI-generated inferences must be distinguishable from confirmed facts.

## 7. Reports and Deliverables

Provide report templates for:

**Executive Intelligence Report**

- Overall digital exposure summary
    
- Major discoveries
    
- Business risk implications
    
- Exposure trends
    
- Recommended actions
    

**Technical OSINT Report**

- Investigation methodology
    
- Scope and source inventory
    
- Detailed discoveries
    
- Infrastructure relationships
    
- Evidence references
    
- Technical recommendations
    

**Continuous Monitoring Report**

- New intelligence
    
- Changed infrastructure
    
- Newly identified exposure
    
- Resolved findings
    
- Historical comparisons
    

Reports should support PDF and CSV exports, scheduled delivery, and customer-specific white labeling.

## 8. SimpleSuite Integration

### SimpleSight + SimpleSec

SimpleSight discovers publicly exposed infrastructure and technology intelligence.

SimpleSec can consume approved discoveries to inform authorized penetration testing scope and testing recommendations.

Discovered assets must not automatically become active test targets without authorization.

### SimpleSight + SimpleShadow

SimpleSight identifies public digital assets, organizational relationships, and exposure indicators.

SimpleShadow enriches approved assets with breach intelligence, leaked credential indicators, and dark web monitoring results.

The platforms share a common finding and asset model while maintaining separate collection engines.

### SimpleSight + SimpleCISO

Validated intelligence findings can create or update risks in SimpleCISO.

Shared information includes:

- Risk title and description
    
- Affected business assets
    
- Severity and supporting evidence
    
- Recommended treatment
    
- Status and ownership
    
- Historical changes
    

### Shared SimpleSuite Services

Plan for centralized:

- Authentication and SSO
    
- Organization and tenant management
    
- Role-based access control
    
- Audit logging
    
- Notifications
    
- Subscription and entitlement management
    
- API access
    
- Shared asset and finding records
    

## 9. Proposed Technical Architecture

**Frontend**

- React / TypeScript
    
- Responsive SaaS dashboard
    
- Interactive relationship graph
    
- Shared SimpleSuite design language
    

**Backend**

- Python / FastAPI or equivalent service architecture
    
- Modular OSINT collection workers
    
- Background job queue
    
- Provider integration adapters
    
- REST API
    
- Scheduled monitoring engine
    

**Data Storage**

- PostgreSQL for tenants, assets, findings, and investigations
    
- Object storage for authorized evidence and report artifacts
    
- Optional graph database when relationship scale justifies it
    
- Redis or equivalent for job coordination and caching
    

**Collection Framework**

- API-first public intelligence adapters
    
- DNS and certificate transparency collectors
    
- Public business information connectors
    
- Public web and archive discovery
    
- Authorized repository exposure intelligence
    
- Provider-specific rate limiting and usage controls
    

**Security Architecture**

- Strict tenant isolation
    
- Encryption in transit and at rest
    
- Centralized secrets management
    
- Least-privilege access
    
- Evidence retention and deletion policies
    
- Source-specific access controls
    
- Audit trails
    
- Collection rate limiting
    
- Terms-of-service and legal compliance
    
- Explicit authorization requirements for active scanning
    

Avoid bypassing authentication, collecting private content, or indiscriminately harvesting personal information.

## 10. Suggested Development Phases

### Phase 1: Minimum Viable Product

Build:

- User authentication
    
- Organization creation and management
    
- Investigation creation
    
- Domain and DNS intelligence
    
- Subdomain and certificate discovery
    
- Public technology identification
    
- Basic findings dashboard
    
- Source provenance
    
- PDF executive reporting
    

### Phase 2: Expanded OSINT

Add:

- Business and organizational records
    
- Public personnel and contact intelligence
    
- Third-party relationship discovery
    
- Public document intelligence
    
- Archive discovery
    
- Cloud exposure indicators
    
- Infrastructure relationship visualization
    

### Phase 3: Advanced Intelligence

Add:

- AI-assisted correlation
    
- Historical discovery comparisons
    
- Continuous monitoring
    
- Scheduled reports
    
- Investigation workflows
    
- Advanced entity relationship graph
    
- Additional intelligence provider integrations
    

### Phase 4: SimpleSuite Integration

Add:

- Shared SimpleSuite authentication
    
- Shared organizational asset inventory
    
- SimpleShadow intelligence enrichment
    
- SimpleCISO risk synchronization
    
- SimpleSec assessment handoff
    
- Shared notifications and reporting
    

## 11. Initial Acceptance Criteria

The MVP is ready for customer testing when:

1. Users can create and manage tenant-isolated organizations.
    
2. Users can initiate passive OSINT investigations against configured organizational domains.
    
3. Collectors return verifiable results with source references and timestamps.
    
4. Results are normalized, deduplicated, and attributed to appropriate assets.
    
5. Findings distinguish confirmed exposure from unverified intelligence.
    
6. Users can review results in a dashboard and export an executive PDF.
    
7. Scan failures, unavailable providers, and partial results are reported accurately.
    
8. API credentials remain protected and collection activity is audited.
    
9. Organizations cannot access other tenants' intelligence or evidence.
    
10. The architecture supports future integration with SimpleSuite services.
    

## 12. Product Vision

SimpleSight will provide organizations with an ongoing understanding of what outsiders can discover about their digital presence.

By combining automated intelligence collection, relationship analysis, AI-assisted interpretation, and integrated risk management, SimpleSight becomes the public intelligence component of SimpleSuite.

**SimpleSight: See What Others Miss.**

_Part of SimpleSuite by Summit Cyber Group._