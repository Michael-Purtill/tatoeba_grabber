import std.stdio;
import std.format;
import std.json;
import requests;
import std.algorithm;

void main()
{
	long pageCount = 0;
	const int perPage = 10; // this is the default perPage value in tatoeba's api.

	const string apiUrl = "https://tatoeba.org/en/api_v0/search";
	const string audioApiUrl = "https://tatoeba.org/en/audio/download/";

	auto statsRes = getContent(apiUrl, ["from": "jpn", "has_audio": "yes", "query": "", "to": "", "page": "1"]);

	JSONValue statsJson = parseJSON(statsRes.toString());

	JSONValue paging = statsJson["paging"];

	pageCount = paging["Sentences"]["pageCount"].integer;

	char[] csvString = cast (char[]) "Sentence, Audio,\n".idup();

	foreach (i; 1..(pageCount + 1)) {
		auto res = getContent(apiUrl, ["from": "jpn", "has_audio": "yes", "query": "", "to": "", "page": "%d".format(i)]);

		JSONValue jsonContent = parseJSON(res.toString());

		JSONValue sentences = jsonContent["results"];

		foreach (s; sentences.array()) {
			string text = s["text"].str;
			long audioId = s["audios"][0]["id"].integer;
			string audioUrl = "%s%d".format(audioApiUrl, audioId);
			csvString ~= "%s,%s,\n".format(text, audioUrl);
		}
	}

	writeln(csvString);
}
