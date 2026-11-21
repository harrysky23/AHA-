export type SceneType = 'introduction'|'evaporation'|'condensation'|'precipitation'|'collection'|'overview'|'text_explanation';
export type Scene = {id:string;type:SceneType;start_seconds:number;end_seconds:number;title:string;explanation:string};
export type Cue = {start_seconds:number;end_seconds:number;text:string};
export type VideoProps = {
  topic:string;fps:number;duration:number;scenes:Scene[];captions:Cue[];
  audio:string|null;background:string|null;audioOffset:number;reviewPrompt:string;
};
