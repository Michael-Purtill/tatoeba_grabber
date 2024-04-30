import std.stdio;
import std.format;
import std.json;
import requests;
import std.algorithm;
import std.getopt;

const string apiUrl = "https://tatoeba.org/en/api_v0/search";
const string audioApiUrl = "https://tatoeba.org/en/audio/download/";

void main(string[] args)
{
	// API OPTIONS
	string langFrom = "";
	string langTo = "";
	bool hasAudio = false;
	long pageCount = 0;

	getopt(args,
		"l|lang", &langFrom,
		"a|audio", &hasAudio
	);

	auto statsRes = getContent(apiUrl, [
			"from": langFrom,
			"has_audio": hasAudio ? "yes": "no",
			"query": "",
			"to": "",
			"page": "1" // seems like tatoeba's api is 1-indexed.
		]);
	
	writeln(statsRes.toString());

	JSONValue statsJson = parseJSON(statsRes.toString());

	JSONValue paging = statsJson["paging"];

	pageCount = paging["Sentences"]["pageCount"].integer;

	// char[] csvString = cast (char[]) "Sentence, Audio,\n".idup();

	foreach (i; 1..(pageCount + 1)) {
	// 	auto res = getContent(apiUrl, ["from": "jpn", "has_audio": "yes", "query": "", "to": "", "page": "%d".format(i)]);

	// 	JSONValue jsonContent = parseJSON(res.toString());

	// 	JSONValue sentences = jsonContentget["results"];

	// 	foreach (s; sentences.array()) {
	// 		string text = s["text"].str;
	// 		long audioId = s["audios"][0]["id"].integer;
	// 		string audioUrl = "%s%d".format(audioApiUrl, audioId);
	// 		csvString ~= "%s,%s,\n".format(text, audioUrl);
	// 	}
	}

	writeln(pageCount);
}
