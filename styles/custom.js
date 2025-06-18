(function() {
  // Configuration
  const CONFIG = {
    defaultVersion: 'v2.13.6',
    versions: [
      {
        wapi: 'v2.13.6',
        niosSupport: 'NIOS: v9.0.6'
      },
      // Add future versions here in the same format
    ],
    defaultSpec: 'dns.json',
    specNamesSorted: true, // Sort spec names alphabetically
    showLoadingIndicator: true // Show a loading indicator while specs load
  };
  
  // Get the version from URL parameter or use default
  const urlParams = new URLSearchParams(window.location.search);
  const currentVersion = urlParams.get('version') || CONFIG.defaultVersion;
  
  // Set base path according to selected version
  const basePath = `swagger-ui/openspec/${currentVersion}`;
  
  // Track loaded state
  let swaggerInitialized = false;
  
  // Wait for the original Swagger UI to initialize
  const checkInterval = setInterval(() => {
    if (window.ui) {
      clearInterval(checkInterval);
      initializeSwaggerUI();
    }
  }, 10);
  
  // Initialize the Swagger UI with our configuration
  function initializeSwaggerUI() {
    // Create specification URLs
    let specUrls = [
      {url: `${basePath}/acl.json`, name: "ACL"},
      {url: `${basePath}/cloud.json`, name: "Cloud"},
      {url: `${basePath}/dhcp.json`, name: "DHCP"},
      {url: `${basePath}/discovery.json`, name: "Discovery"},
      {url: `${basePath}/dns.json`, name: "DNS"},
      {url: `${basePath}/dtc.json`, name: "DTC"},
      {url: `${basePath}/federatedrealms.json`, name: "Federated Realms"},
      {url: `${basePath}/grid.json`, name: "Grid"},
      {url: `${basePath}/ipam.json`, name: "IPAM"},
      {url: `${basePath}/microsoftserver.json`, name: "Microsoft Server"},
      {url: `${basePath}/misc.json`, name: "Misc"},
      {url: `${basePath}/notification.json`, name: "Notification"},
      {url: `${basePath}/parentalcontrol.json`, name: "Parental Control"},
      {url: `${basePath}/rir.json`, name: "RIR"},
      {url: `${basePath}/rpz.json`, name: "RPZ"},
      {url: `${basePath}/security.json`, name: "Security"},
      {url: `${basePath}/smartfolder.json`, name: "Smart Folder"},
      {url: `${basePath}/threatinsight.json`, name: "Threat Insight"},
      {url: `${basePath}/threatprotection.json`, name: "Threat Protection"}
    ];
    
    // Sort specs alphabetically if configured
    if (CONFIG.specNamesSorted) {
      specUrls.sort((a, b) => a.name.localeCompare(b.name));
    }

    // Initialize Swagger UI with error handling
    try {
      window.ui = SwaggerUIBundle({
        url: `${basePath}/${CONFIG.defaultSpec}`,
        urls: specUrls,
        dom_id: '#swagger-ui',
        deepLinking: true,
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIStandalonePreset
        ],
        plugins: [
          SwaggerUIBundle.plugins.DownloadUrl
        ],
        layout: "StandaloneLayout",
        supportedSubmitMethods: [],
        onComplete: function() {
          // UI fully rendered
          swaggerInitialized = true;
        }
      });
    } catch (e) {
      console.error("Failed to initialize Swagger UI:", e);
      document.getElementById('swagger-ui').innerHTML = 
        `<div style="padding: 20px; text-align: center;">
          <h3>Error loading API documentation</h3>
          <p>There was a problem loading the specification for ${currentVersion}.</p>
          <p>Error details: ${e.message}</p>
        </div>`;
    }

    // Set up observers for UI elements
    setupUIObservers();
  }
  
  // Setup the MutationObservers for the UI elements
  function setupUIObservers() {
    // Single observer for all UI elements
    const observer = new MutationObserver((mutations) => {
      // Check for topbar
      const topbar = document.querySelector('.topbar .download-url-wrapper');
      if (topbar) {
        observer.disconnect(); // Stop observing once found
        addWapiVersionToTopbar(topbar, currentVersion);
      }
    });
    
    // Start observing with a single observer
    observer.observe(document.body, { 
      childList: true, 
      subtree: true 
    });
  }
  
  // Function to add WAPI version to topbar
  function addWapiVersionToTopbar(topbar, currentVersion) {
    // Create HTML for the WAPI version selector
    const wapiVersionHTML = `
      <div class="download-url-wrapper wapi-version-wrapper" style="margin-left: 15px;">
        <label class="select-label" for="wapi-version-selector">
          <span>WAPI Version</span>
          <select id="wapi-version-selector">
            ${CONFIG.versions.map(version => 
              `<option value="${version.wapi}" ${version.wapi === currentVersion ? 'selected' : ''}>${version.wapi} (${version.niosSupport})</option>`
            ).join('')}
          </select>
        </label>
      </div>
    `;
    
    // Check if selector is already added
    if (!document.getElementById('wapi-version-selector')) {
      // Insert after the existing dropdown
      topbar.insertAdjacentHTML('afterend', wapiVersionHTML);
      
      // Add event listener
      document.getElementById('wapi-version-selector').addEventListener('change', (e) => {
        const newVersion = e.target.value;
        const newUrl = new URL(window.location.href);
        newUrl.searchParams.set('version', newVersion);
        window.location.href = newUrl.toString();
      });
    }
  }
  
  // Helper to create version change URL
  function createVersionURL(version) {
    const url = new URL(window.location.href);
    url.searchParams.set('version', version);
    return url.toString();
  }
})();
