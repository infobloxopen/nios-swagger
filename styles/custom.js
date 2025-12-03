(function() {
  // CORS Proxy Configuration - can be overridden by server/environment
  const CORS_PROXY = {
    enabled: window.CORS_PROXY_CONFIG?.enabled ?? true,
    proxyUrl: window.CORS_PROXY_CONFIG?.proxyUrl ?? 'http://localhost:8000',
    // Patterns to match NIOS requests
    niosPatterns: [
      /^https?:\/\/[\d.]+\/wapi\//,           // IP addresses
      /^https?:\/\/[^\/]+\/wapi\//            // Hostnames
    ]
  };

  // Function to check if URL should be proxied
  function shouldProxy(url) {
    if (!CORS_PROXY.enabled) return false;
    return CORS_PROXY.niosPatterns.some(pattern => pattern.test(url));
  }

  // Function to convert NIOS URL to proxy URL
  function convertToProxyUrl(originalUrl) {
    if (!shouldProxy(originalUrl)) return originalUrl;

    try {
      const url = new URL(originalUrl);
      const NIOS_Grid_IP = url.hostname;
      const path = url.pathname + url.search;

      // Convert https://localhost/wapi/v2.13.6/namedacl
      // To: http://localhost:8001/localhost/wapi/v2.13.6/namedacl
      return `${CORS_PROXY.proxyUrl}/${NIOS_Grid_IP}${path}`;
    } catch (e) {
      console.warn('Failed to convert URL to proxy:', originalUrl, e);
      return originalUrl;
    }
  }

  // Intercept fetch requests
  const originalFetch = window.fetch;
  window.fetch = function(resource, options = {}) {
    const url = typeof resource === 'string' ? resource : resource.url;
    const proxyUrl = convertToProxyUrl(url);

    if (url !== proxyUrl) {
      console.log(`[CORS Proxy] Routing ${url} -> ${proxyUrl}`);

      // Update the resource with proxy URL
      if (typeof resource === 'string') {
        resource = proxyUrl;
      } else {
        resource = new Request(proxyUrl, resource);
      }
    }

    return originalFetch.call(this, resource, options);
  };

  // Intercept XMLHttpRequest
  const originalXHROpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url, ...args) {
    const proxyUrl = convertToProxyUrl(url);

    if (url !== proxyUrl) {
      console.log(`[CORS Proxy] Routing XMLHttpRequest ${url} -> ${proxyUrl}`);
      url = proxyUrl;
    }

    return originalXHROpen.call(this, method, url, ...args);
  };

  // Configuration
  const CONFIG = {
    defaultVersion: 'v2.13.8',
    versions: [
      {
        wapi: 'v2.13.8',
        niosSupport: 'NIOS: v9.0.8'
      },
      {
        wapi: 'v2.13.7',
        niosSupport: 'NIOS: v9.0.7'
      },
      {
        wapi: 'v2.13.6',
        niosSupport: 'NIOS: v9.0.6'
      },
      {
        wapi: 'v2.13.1',
        niosSupport: 'NIOS: v9.0.1 - v9.0.3'

      }
      // Add future versions here in the same format
    ],
    defaultSpec: 'dns.json',
    specNamesSorted: true, // Sort spec names alphabetically
    showLoadingIndicator: true // Show a loading indicator while specs load
  };

  // LocalStorage key for persisting server NIOS_Grid_IP
  const STORAGE_KEY = 'nios-swagger-server-NIOS_Grid_IP';

  // Functions to manage server URL persistence
  function saveServerUrl(baseUrl) {
    try {
      localStorage.setItem(STORAGE_KEY, baseUrl);
    } catch (e) {
      console.warn('Failed to save server URL to localStorage:', e);
    }
  }

  function getSavedServerUrl() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      console.warn('Failed to retrieve server URL from localStorage:', e);
      return null;
    }
  }

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

  // Create a plugin to persist server variables
  const ServerPersistencePlugin = function() {
    return {
      statePlugins: {
        spec: {
          wrapActions: {
            updateSpec: (oriAction) => (spec) => {
              // Modify the spec to include our saved server URL before processing
              const savedUrl = getSavedServerUrl();

              if (savedUrl) {
                try {
                  let specObj;
                  let isString = typeof spec === 'string';

                  // Parse spec if it's a string
                  if (isString) {
                    specObj = JSON.parse(spec);
                  } else if (spec && typeof spec === 'object') {
                    // Clone the object to avoid mutating the original
                    specObj = JSON.parse(JSON.stringify(spec));
                  }

                  // Update the server variable default
                  if (specObj && specObj.servers && specObj.servers[0] &&
                      specObj.servers[0].variables && specObj.servers[0].variables.NIOS_Grid_IP) {
                    specObj.servers[0].variables.NIOS_Grid_IP.default = savedUrl;

                    // Convert back to string if needed
                    spec = isString ? JSON.stringify(specObj) : specObj;
                  }
                } catch (e) {
                  console.warn('[ServerPersistence] Failed to modify spec:', e);
                }
              }
              // Call original action with modified spec
              return oriAction(spec);
            }
          }
        }
      }
    };
  };

  // Function to restore the saved server URL in the UI
  function restoreServerUrl(system) {
    const savedUrl = getSavedServerUrl();

    if (!savedUrl || !system) {
      return;
    }

    try {
      // Use the oas3 actions to set the server variable
      if (system.oas3Actions && system.oas3Actions.setSelectedServer) {
        const spec = system.specSelectors.spec();
        if (spec && spec.toJS) {
          const specJson = spec.toJS();
          if (specJson.servers && specJson.servers[0]) {
            const serverUrl = specJson.servers[0].url;

            // Set the selected server
            system.oas3Actions.setSelectedServer(serverUrl);

            // Set the server variable value
            if (system.oas3Actions.setServerVariableValue) {
              system.oas3Actions.setServerVariableValue({
                server: serverUrl,
                key: 'NIOS_Grid_IP',
                val: savedUrl
              });
            }
          }
        }
      }
    } catch (e) {
      console.warn('[ServerPersistence] Failed to restore server URL in UI:', e);
    }
  }

  // Function to monitor and manage the server input field
  function monitorServerInput() {
    const processedInputs = new WeakSet();

    // Function to setup input field
    function setupServerInput(input) {
      // Avoid re-processing the same input
      if (processedInputs.has(input)) return;
      processedInputs.add(input);

      // Restore saved value
      const savedUrl = getSavedServerUrl();
      if (savedUrl && input.value !== savedUrl) {
        input.value = savedUrl;
        // Trigger input event to update Swagger UI's state
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
      }

      // Listen for changes and save to localStorage
      const saveHandler = () => {
        const newValue = input.value;
        if (newValue && newValue.trim() !== '') {
          saveServerUrl(newValue);

          // Also update Swagger UI state when user changes value
          try {
            if (window.ui && window.ui.oas3Actions) {
              const spec = window.ui.specSelectors.spec();
              if (spec && spec.toJS) {
                const specJson = spec.toJS();
                if (specJson.servers && specJson.servers[0]) {
                  const serverUrl = specJson.servers[0].url;
                  window.ui.oas3Actions.setServerVariableValue({
                    server: serverUrl,
                    key: 'NIOS_Grid_IP',
                    val: newValue
                  });
                }
              }
            }
          } catch (e) {
            console.warn('Failed to update server variable:', e);
          }
        }
      };

      input.addEventListener('change', saveHandler);
      input.addEventListener('blur', saveHandler);
    }

    // Function to check and setup all server inputs
    function checkServerInputs() {
      // Look for the server variable input field
      const serverInputs = document.querySelectorAll('.servers input[type="text"], input[placeholder*="NIOS_Grid_IP"], input[aria-label*="NIOS_Grid_IP"]');

      serverInputs.forEach(input => {
        setupServerInput(input);
      });

      // Also check for any input in the servers wrapper
      const serversWrapper = document.querySelector('.servers');
      if (serversWrapper) {
        const inputs = serversWrapper.querySelectorAll('input[type="text"]');
        inputs.forEach(input => {
          setupServerInput(input);
        });
      }
    }

    // Create observer to watch for server input field and spec changes
    const observer = new MutationObserver(() => {
      checkServerInputs();
    });

    // Start observing
    observer.observe(document.body, {
      childList: true,
      subtree: true
    });

    // Monitor the spec selector dropdown for changes
    const checkSpecSelector = setInterval(() => {
      const specSelector = document.querySelector('.download-url-wrapper select');
      if (specSelector && !specSelector.hasAttribute('data-monitored')) {
        specSelector.setAttribute('data-monitored', 'true');
        specSelector.addEventListener('change', () => {
          // When spec changes, wait for it to load then restore
          setTimeout(() => {
            restoreServerUrl(window.ui);
            checkServerInputs();
          }, 500);
        });
        // Clear the interval once we've found and setup the selector
        clearInterval(checkSpecSelector);
      }
    }, 500);

    // Check immediately
    setTimeout(checkServerInputs, 500);
    setTimeout(checkServerInputs, 1000);
    setTimeout(checkServerInputs, 2000);
  }

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

  // Only add Federated Realms for versions other than 2.13.1
  if (currentVersion !== 'v2.13.1') {
    specUrls.push({url: `${basePath}/federatedrealms.json`, name: "Federated Realms"});
  }
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
          SwaggerUIBundle.plugins.DownloadUrl,
          ServerPersistencePlugin
        ],
        layout: "StandaloneLayout",
        onComplete: function() {
          // UI fully rendered
          swaggerInitialized = true;
          // Restore saved server URL when UI is ready
          restoreServerUrl(window.ui);
          // Start monitoring server input field
          monitorServerInput();
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
