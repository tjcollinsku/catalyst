import { ExternalSearchLauncher } from "../types";

const STORAGE_KEY = "catalyst_external_search_launchers";

const DEFAULT_LAUNCHERS: ExternalSearchLauncher[] = [
    {
        id: "google-news",
        name: "Google News",
        urlTemplate: "https://news.google.com/search?q={q}",
    },
    {
        id: "newspapers",
        name: "Newspapers.com",
        urlTemplate: "https://www.newspapers.com/search/?query={q}",
    },
    {
        id: "legacy",
        name: "Legacy.com (Obituaries)",
        urlTemplate: "https://www.legacy.com/us/obituaries/name/{q}",
    },
    {
        id: "find-a-grave",
        name: "Find-a-Grave",
        urlTemplate: "https://www.findagrave.com/memorial/search?firstname=&lastname={q}",
    },
    {
        id: "ohio-ecourts",
        name: "Ohio eCourts",
        urlTemplate: "https://www.courtclerk.org/records-search/?q={q}",
    },
    {
        id: "pacer",
        name: "PACER (Federal Courts)",
        urlTemplate: "https://pcl.uscourts.gov/pcl/pages/search/results/parties?lastName={q}",
    },
    {
        id: "ohio-sos",
        name: "Ohio Secretary of State",
        urlTemplate: "https://businesssearch.ohiosos.gov/?=&SearchType=&QueryString={q}",
    },
];

export function loadLaunchers(): ExternalSearchLauncher[] {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (raw) return JSON.parse(raw);
    } catch {
        // fall through
    }
    return DEFAULT_LAUNCHERS;
}

export function saveLaunchers(launchers: ExternalSearchLauncher[]): void {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(launchers));
    } catch {
        // localStorage full or unavailable
    }
}

export function resetLaunchersToDefaults(): ExternalSearchLauncher[] {
    saveLaunchers(DEFAULT_LAUNCHERS);
    return DEFAULT_LAUNCHERS;
}

export function buildSearchUrl(template: string, query: string): string {
    return template.replace(/\{q\}/g, encodeURIComponent(query));
}
