import { useMemo, useState } from "react";
import { geoEquirectangular, geoGraticule10, geoPath } from "d3-geo";
import { feature } from "topojson-client";
import type { FeatureCollection, GeoJsonProperties, Geometry } from "geojson";
import worldAtlas from "world-atlas/countries-110m.json";
import { useParams } from "react-router-dom";

import { EmptyState } from "../components/EmptyState";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingBlock } from "../components/LoadingBlock";
import { PageHeader } from "../components/PageHeader";
import { apiClient } from "../lib/api/client";
import { useAsyncData } from "../lib/hooks";
import type { MapEntity, MapLink, MapOverlay } from "../lib/models";
import { appRoutes } from "../routes";

const MAP_WIDTH = 1080;
const MAP_HEIGHT = 540;

const projection = geoEquirectangular()
  .fitExtent(
    [
      [0, 0],
      [MAP_WIDTH, MAP_HEIGHT]
    ],
    { type: "Sphere" }
  )
  .precision(0.2);
const pathGenerator = geoPath(projection);
const graticulePath = pathGenerator(geoGraticule10()) ?? "";
const spherePath = pathGenerator({ type: "Sphere" }) ?? "";
const worldFeatures = feature(
  worldAtlas as any,
  (worldAtlas as any).objects.countries
) as unknown as FeatureCollection<Geometry, GeoJsonProperties>;
const countryPaths = worldFeatures.features
  .map((country, index) => ({ id: String(country.id ?? index), path: pathGenerator(country) ?? "" }))
  .filter(country => country.path);
const LONGITUDE_LABELS = [-150, -120, -90, -60, -30, 0, 30, 60, 90, 120, 150];
const LATITUDE_LABELS = [-60, -30, 0, 30, 60];

type LayerState = {
  satellites: boolean;
  ground: boolean;
  extras: boolean;
  links: boolean;
  tracks: boolean;
  coverage: boolean;
  labels: boolean;
  overlays: boolean;
};

function project(lat: number, lon: number) {
  const point = projection([lon, lat]);
  if (point) {
    return { x: point[0], y: point[1] };
  }
  return {
    x: ((lon + 180) / 360) * MAP_WIDTH,
    y: ((90 - lat) / 180) * MAP_HEIGHT
  };
}

function entityClass(entity: MapEntity) {
  if (entity.status === "damaged") {
    return "map-marker map-marker-damaged";
  }
  return `map-marker map-marker-${entity.entity_type}`;
}

function entityRadius(entity: MapEntity) {
  if (entity.entity_type === "satellite") {
    return 4.5;
  }
  if (entity.entity_type === "ground_station") {
    return 7;
  }
  return 6;
}

function isLayerVisible(entity: MapEntity, layers: LayerState) {
  if (entity.entity_type === "satellite") {
    return layers.satellites;
  }
  if (entity.entity_type === "ground_station") {
    return layers.ground;
  }
  if (entity.entity_type === "extra_node") {
    return layers.extras;
  }
  return true;
}

function linkSegments(link: MapLink, entityById: Map<string, MapEntity>) {
  const source = entityById.get(link.source);
  const target = entityById.get(link.target);
  if (!source || !target) {
    return [];
  }
  const sourcePoint = project(source.lat, source.lon);
  const targetPoint = project(target.lat, target.lon);
  if (Math.abs(source.lon - target.lon) <= 180) {
    return [{ source: sourcePoint, target: targetPoint }];
  }

  const left = source.lon < target.lon ? source : target;
  const right = source.lon < target.lon ? target : source;
  const leftPoint = project(left.lat, left.lon);
  const rightPoint = project(right.lat, right.lon);
  return [
    { source: leftPoint, target: { x: 0, y: leftPoint.y } },
    { source: { x: MAP_WIDTH, y: rightPoint.y }, target: rightPoint }
  ];
}

function coordinateSegments(points: MapEntity[], closePath = false) {
  const sortedPoints = closePath && points.length > 2 ? [...points, points[0]] : points;
  const segments: Array<{ source: { x: number; y: number }; target: { x: number; y: number } }> = [];
  for (let index = 1; index < sortedPoints.length; index += 1) {
    const source = sortedPoints[index - 1];
    const target = sortedPoints[index];
    if (Math.abs(source.lon - target.lon) > 180) {
      continue;
    }
    segments.push({ source: project(source.lat, source.lon), target: project(target.lat, target.lon) });
  }
  return segments;
}

function orbitTrackSegments(entities: MapEntity[]) {
  const groups = new Map<string, MapEntity[]>();
  entities.forEach(entity => {
    if (entity.entity_type !== "satellite" || entity.shell === null || entity.orbit === null) {
      return;
    }
    const key = `${entity.shell}-${entity.orbit}`;
    groups.set(key, [...(groups.get(key) ?? []), entity]);
  });

  return Array.from(groups.entries()).flatMap(([key, group]) =>
    coordinateSegments(
      group.sort((left, right) => (left.satellite ?? 0) - (right.satellite ?? 0)),
      true
    ).map((segment, index) => ({ ...segment, key: `${key}-${index}` }))
  );
}

function overlayEntityIds(overlays: MapOverlay[]) {
  const ids = new Set<string>();
  overlays.forEach(overlay => overlay.entity_ids.forEach(id => ids.add(id)));
  return ids;
}

function formatCoordinate(value: number, axis: "lat" | "lon") {
  const suffix = axis === "lat" ? (value >= 0 ? "N" : "S") : value >= 0 ? "E" : "W";
  return `${Math.abs(value).toFixed(3)} ${suffix}`;
}

export function RunMapPage() {
  const { runId = "" } = useParams();
  const [time, setTime] = useState(0);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [layers, setLayers] = useState<LayerState>({
    satellites: true,
    ground: true,
    extras: true,
    links: true,
    tracks: true,
    coverage: true,
    labels: false,
    overlays: true
  });
  const mapState = useAsyncData(() => apiClient.getMap(runId, time), [runId, time]);

  const entityById = useMemo(
    () => new Map((mapState.data?.entities ?? []).map(entity => [entity.id, entity])),
    [mapState.data]
  );
  const activeOverlayIds = useMemo(
    () => overlayEntityIds(layers.overlays ? mapState.data?.overlays ?? [] : []),
    [layers.overlays, mapState.data]
  );
  const filteredEntities = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return (mapState.data?.entities ?? []).filter(entity => {
      if (!isLayerVisible(entity, layers)) {
        return false;
      }
      if (!normalized) {
        return true;
      }
      return entity.name.toLowerCase().includes(normalized) || entity.entity_type.toLowerCase().includes(normalized);
    });
  }, [layers, mapState.data, query]);
  const visibleEntityIds = useMemo(() => new Set(filteredEntities.map(entity => entity.id)), [filteredEntities]);
  const selectedEntity = selectedEntityId ? entityById.get(selectedEntityId) ?? null : null;
  const selectedOverlays = useMemo(
    () => (mapState.data?.overlays ?? []).filter(overlay => selectedEntityId && overlay.entity_ids.includes(selectedEntityId)),
    [mapState.data, selectedEntityId]
  );
  const selectedLinks = useMemo(
    () => (mapState.data?.links ?? []).filter(link => selectedEntityId && (link.source === selectedEntityId || link.target === selectedEntityId)),
    [mapState.data, selectedEntityId]
  );
  const selectedPeerIds = useMemo(
    () =>
      new Set(
        selectedLinks.map(link => (link.source === selectedEntityId ? link.target : link.source))
      ),
    [selectedEntityId, selectedLinks]
  );
  const trackSegments = useMemo(
    () => orbitTrackSegments((mapState.data?.entities ?? []).filter(entity => visibleEntityIds.has(entity.id))),
    [mapState.data, visibleEntityIds]
  );
  const duration = Math.max(0, (mapState.data?.duration_s ?? 1) - 1);
  const step = Math.max(1, mapState.data?.step_s ?? 1);
  const experimentId = mapState.data?.experiment_id;

  function updateLayer(name: keyof LayerState) {
    setLayers(current => ({ ...current, [name]: !current[name] }));
  }

  function stepTime(direction: -1 | 1) {
    setTime(current => Math.max(0, Math.min(duration, current + direction * step)));
  }

  return (
    <section className="page-stack">
      <PageHeader
        tone="topology"
        breadcrumbs={[
          { label: "Experiments", to: appRoutes.experiments() },
          experimentId
            ? { label: experimentId, to: appRoutes.experimentDetailPath(experimentId) }
            : { label: "Experiment" },
          { label: runId, to: appRoutes.runDetailPath(runId) },
          { label: "Map" }
        ]}
        title="Map"
        actions={
          <div className="map-time-actions">
            <button className="ghost-button" onClick={() => stepTime(-1)} disabled={time <= 0}>
              Prev
            </button>
            <label className="time-control">
              <span>Time</span>
              <input
                type="number"
                min={0}
                max={duration}
                step={step}
                value={time}
                onChange={event => setTime(Math.max(0, Number(event.target.value) || 0))}
              />
            </label>
            <button className="ghost-button" onClick={() => stepTime(1)} disabled={time >= duration}>
              Next
            </button>
          </div>
        }
      />

      {mapState.loading ? <LoadingBlock /> : null}
      {mapState.error ? <ErrorPanel message={mapState.error.message} /> : null}

      {mapState.data ? (
        mapState.data.entities.length ? (
          <>
            <section className="metric-grid">
              <div className="metric-card">
                <p className="metric-label">Satellites</p>
                <p className="metric-value">{mapState.data.summary.satellites}</p>
              </div>
              <div className="metric-card">
                <p className="metric-label">Ground stations</p>
                <p className="metric-value">{mapState.data.summary.ground_stations}</p>
              </div>
              <div className="metric-card">
                <p className="metric-label">Extra nodes</p>
                <p className="metric-value">{mapState.data.summary.extra_nodes}</p>
              </div>
              <div className="metric-card">
                <p className="metric-label">Links</p>
                <p className="metric-value">{mapState.data.summary.links}</p>
              </div>
            </section>

            <div className="map-workbench">
              <section className="map-canvas-panel">
                <div className="map-toolbar">
                  <input
                    className="map-search"
                    value={query}
                    onChange={event => setQuery(event.target.value)}
                    placeholder="Filter nodes"
                  />
                  <div className="map-layer-toggles">
                    {([
                      ["satellites", "Sat"],
                      ["ground", "GS"],
                      ["extras", "Extra"],
                      ["links", "Links"],
                      ["tracks", "Tracks"],
                      ["coverage", "Coverage"],
                      ["labels", "Labels"],
                      ["overlays", "Overlays"]
                    ] as [keyof LayerState, string][]).map(([key, label]) => (
                      <label key={key} className="map-toggle">
                        <input type="checkbox" checked={layers[key]} onChange={() => updateLayer(key)} />
                        <span>{label}</span>
                      </label>
                    ))}
                  </div>
                </div>

                <input
                  className="map-time-slider"
                  type="range"
                  min={0}
                  max={duration}
                  step={step}
                  value={Math.min(time, duration)}
                  onChange={event => setTime(Number(event.target.value))}
                />

                <svg viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`} className="geo-map" role="img">
                  <defs>
                    <radialGradient id="map-ocean-gradient" cx="50%" cy="40%" r="76%">
                      <stop offset="0%" stopColor="#f5fbff" />
                      <stop offset="58%" stopColor="#d9e8f2" />
                      <stop offset="100%" stopColor="#c8dce9" />
                    </radialGradient>
                    <filter id="map-glow" x="-30%" y="-30%" width="160%" height="160%">
                      <feGaussianBlur stdDeviation="4" result="blur" />
                      <feMerge>
                        <feMergeNode in="blur" />
                        <feMergeNode in="SourceGraphic" />
                      </feMerge>
                    </filter>
                  </defs>
                  <path d={spherePath} className="map-sphere" />
                  <path d={graticulePath} className="map-graticule" />
                  {countryPaths.map(country => (
                    <path key={country.id} d={country.path} className="map-land" />
                  ))}
                  {LONGITUDE_LABELS.map(lon => {
                    const p = project(-82, lon);
                    return (
                      <text key={`lon-label-${lon}`} x={p.x} y={p.y} className="map-axis-label">
                        {lon === 0 ? "0" : `${Math.abs(lon)}${lon < 0 ? "W" : "E"}`}
                      </text>
                    );
                  })}
                  {LATITUDE_LABELS.map(lat => {
                    const p = project(lat, -177);
                    return (
                      <text key={`lat-label-${lat}`} x={p.x} y={p.y} className="map-axis-label map-axis-label-lat">
                        {lat === 0 ? "EQ" : `${Math.abs(lat)}${lat < 0 ? "S" : "N"}`}
                      </text>
                    );
                  })}

                  {layers.tracks
                    ? trackSegments.map(segment => (
                        <line
                          key={segment.key}
                          x1={segment.source.x}
                          y1={segment.source.y}
                          x2={segment.target.x}
                          y2={segment.target.y}
                          className="map-orbit-track"
                        />
                      ))
                    : null}

                  {layers.links
                    ? mapState.data.links.map(link => {
                        if (!visibleEntityIds.has(link.source) || !visibleEntityIds.has(link.target)) {
                          return null;
                        }
                        return linkSegments(link, entityById).map((segment, index) => (
                          <line
                            key={`${link.source}-${link.target}-${index}`}
                            x1={segment.source.x}
                            y1={segment.source.y}
                            x2={segment.target.x}
                            y2={segment.target.y}
                            className={
                              selectedEntityId && (link.source === selectedEntityId || link.target === selectedEntityId)
                                ? `map-link map-link-selected map-link-${link.link_type}`
                                : `map-link map-link-${link.link_type}`
                            }
                          />
                        ));
                      })
                    : null}

                  {filteredEntities.map(entity => {
                    const point = project(entity.lat, entity.lon);
                    const selected = entity.id === selectedEntityId;
                    const peer = selectedPeerIds.has(entity.id);
                    const highlighted = activeOverlayIds.has(entity.id);
                    return (
                      <g
                        key={entity.id}
                        className={selected ? "map-entity map-entity-selected" : peer ? "map-entity map-entity-peer" : "map-entity"}
                        onClick={() => setSelectedEntityId(entity.id)}
                      >
                        {layers.coverage && entity.entity_type === "ground_station" ? (
                          <circle cx={point.x} cy={point.y} r={58} className="map-ground-coverage" />
                        ) : null}
                        {layers.coverage && selected && entity.entity_type === "satellite" ? (
                          <circle cx={point.x} cy={point.y} r={32} className="map-sat-coverage" />
                        ) : null}
                        {highlighted ? <circle cx={point.x} cy={point.y} r={entityRadius(entity) + 7} className="map-overlay-halo" /> : null}
                        <circle cx={point.x} cy={point.y} r={entityRadius(entity)} className={entityClass(entity)} />
                        {layers.labels || selected ? (
                          <text x={point.x + 8} y={point.y - 8} className="map-label">
                            {entity.name}
                          </text>
                        ) : null}
                      </g>
                    );
                  })}
                  <g className="map-legend" transform="translate(18 18)">
                    <rect width="188" height="118" rx="8" />
                    <text x="12" y="22" className="map-legend-title">Layers</text>
                    <circle cx="18" cy="45" r="5" className="map-marker map-marker-satellite" />
                    <text x="32" y="49">Satellite</text>
                    <circle cx="18" cy="67" r="6" className="map-marker map-marker-ground_station" />
                    <text x="32" y="71">Ground station</text>
                    <line x1="12" y1="90" x2="28" y2="90" className="map-link map-link-ground-satellite" />
                    <text x="32" y="94">Active link</text>
                  </g>
                </svg>
              </section>

              <aside className="inspector-panel map-inspector">
                <h3>Map detail</h3>
                {selectedEntity ? (
                  <>
                    <dl className="detail-grid">
                      <div>
                        <dt>Name</dt>
                        <dd>{selectedEntity.name}</dd>
                      </div>
                      <div>
                        <dt>Type</dt>
                        <dd>{selectedEntity.entity_type}</dd>
                      </div>
                      <div>
                        <dt>Status</dt>
                        <dd>{selectedEntity.status}</dd>
                      </div>
                      <div>
                        <dt>Position</dt>
                        <dd>
                          {formatCoordinate(selectedEntity.lat, "lat")}, {formatCoordinate(selectedEntity.lon, "lon")}
                        </dd>
                      </div>
                      <div>
                        <dt>Altitude</dt>
                        <dd>{selectedEntity.altitude_km.toFixed(2)} km</dd>
                      </div>
                      <div>
                        <dt>Neighbors</dt>
                        <dd>{selectedEntity.neighbor_count}</dd>
                      </div>
                    </dl>

                    <div className="map-inspector-section">
                      <p className="eyebrow">Links</p>
                      <div className="map-chip-list">
                        {selectedLinks.map(link => (
                          <span key={`${link.source}-${link.target}`} className="map-chip">
                            {link.source === selectedEntity.id ? link.target : link.source}
                          </span>
                        ))}
                        {!selectedLinks.length ? <span className="map-chip">None</span> : null}
                      </div>
                    </div>

                    <div className="map-inspector-section">
                      <p className="eyebrow">Overlays</p>
                      <div className="map-overlay-list">
                        {selectedOverlays.map(overlay => (
                          <div key={overlay.id} className={`map-overlay-item map-overlay-${overlay.severity}`}>
                            <strong>{overlay.label}</strong>
                            <span>{overlay.time === null ? "runtime" : `${overlay.time}s`}</span>
                          </div>
                        ))}
                        {!selectedOverlays.length ? <p className="page-description">No overlays for this entity.</p> : null}
                      </div>
                    </div>
                  </>
                ) : (
                  <p className="page-description">Select a map entity to inspect location, links, events, and tasks.</p>
                )}
              </aside>
            </div>
          </>
        ) : (
          <EmptyState title="No map data" body="The run exists, but no geospatial entities are available for this time." />
        )
      ) : null}
    </section>
  );
}
